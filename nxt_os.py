import streamlit as st
# Versão: 1.2.0 - Fix: Intelligent Mapping Reload
import pandas as pd
import numpy as np
import io
import re
import os
import time
from datetime import datetime

# Importações do NXT Automation
import automacao_nxt as auto

# ───────────────────────────── Configuração da Página ─────────────────────────
st.set_page_config(
    page_title="NXT OS — CRM Inteligente",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilo Premium (CSS Customizado)
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #2e7d32;
        color: white;
        font-weight: bold;
        border: none;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #388e3c;
        transform: scale(1.02);
    }
    .card {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #333;
        margin-bottom: 20px;
        transition: 0.3s;
    }
    .card:hover {
        border-color: #2e7d32;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }
    .company-name {
        font-size: 1.2em;
        font-weight: bold;
        color: #fff;
    }
    .diagnostico {
        font-size: 0.9em;
        color: #bbb;
        margin-top: 10px;
        font-style: italic;
    }
    .status-badge {
        background-color: #333;
        color: #ddd;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.8em;
    }
    </style>
""", unsafe_allow_html=True)

# ───────────────────────────── Sidebar & Navegação ────────────────────────────
# ── Sidebar: Menu e Info ──
st.sidebar.image("https://nxt-leads.vercel.app/logo-nxt.png", width=150)
st.sidebar.markdown("### 🛰️ NXT OS")
st.sidebar.info("v1.4.0 Beta — *Evolução Progressiva*")

menu = st.sidebar.radio(
    "Navegação",
    ["📊 Dashboard", "📥 Importação", "🎯 Disparos", "🔁 Follow Up", "📈 Métricas", "🧬 Evolution History"],
    index=1
)

st.sidebar.divider()

# ─── HELPERS DO PURIFIER ────────────────────────────────────────────────────
def _find_status_candidate(contact_col: str, all_cols: list) -> int:
    """Auto-sugestão de coluna de status para o Smart Erase."""
    contact_lower = contact_col.lower()
    num_match = re.search(r"(\d+)", contact_lower)
    suffix = num_match.group(1) if num_match else None
    root = re.split(r"[_\s]*\d", contact_lower)[0].strip("_ ")
    for priority_fn in [
        lambda c: (suffix and suffix in c and root and root in c and "status" in c),
        lambda c: (suffix and suffix in c and "status" in c),
        lambda c: (root and root in c and "status" in c),
    ]:
        for idx, col in enumerate(all_cols):
            col_lower = col.lower()
            if col_lower == contact_lower:
                continue
            if priority_fn(col_lower):
                return idx
    return 0

# ───────────────────────────── MÓDULO: DASHBOARD ─────────────────────────────
if menu == "📊 Dashboard":
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.title("🚀 NXT OS — Command Center")
    with col_h2:
        if st.button("🔄 Sincronizar", key="dash_sync"):
            auto.buscar_dados_completos.clear()
            st.rerun()

    with st.spinner("Sincronizando dados do Notion..."):
        dados_raw = auto.buscar_dados_completos()

    if not dados_raw:
        st.warning("⚠️ Sem dados. Verifique as credenciais do Notion ou faça uma importação primeiro.")
    else:
        df_dash = pd.DataFrame(dados_raw)

        # DEBUG (apenas se necessário ver as colunas)
        with st.expander("🔍 Depuração de Dados", expanded=False):
            st.write("Colunas detetadas:", df_dash.columns.tolist())
            st.write("Amostra de dados (primeiras 3 linhas):")
            st.write(df_dash.head(3))

        # ── Cálculos de Inteligência ──
        total       = len(df_dash)
        convertidos = int((df_dash["Status de Contato"] == "Convertido").sum())
        taxa_conv   = f"{(convertidos / total * 100):.1f}%" if total > 0 else "0.0%"

        # Capital em Negociação
        status_negocio = ['Aguardando retorno', 'Respondeu', 'Reunião agendada']
        capital_neg = df_dash[df_dash["Status de Contato"].isin(status_negocio)]["Valor Potencial"].sum()

        # Taxa de Decisores
        total_ativos = total # Consideramos todos na base como ativos para esta métrica
        decisores_sim = int(df_dash["Decisor"].str.contains("Sim", na=False).sum())
        taxa_decisores = f"{(decisores_sim / total_ativos * 100):.1f}%" if total_ativos > 0 else "0.0%"

        # Taxa de Resposta
        # Resposta = qualquer status que não seja "Não contactado", "Tentativa de contato" ou vazio
        status_ignorados = ["Não contactado", "Tentativa de contato", "", "Arquivar"]
        respostas = int((~df_dash["Status de Contato"].isin(status_ignorados)).sum())
        taxa_resposta = f"{(respostas / total * 100):.1f}%" if total > 0 else "0.0%"

        # ── Linha 1: Métricas de Conversão ──
        c1, c2, c3 = st.columns(3)
        c1.metric("📊 Total de Leads", total)
        c2.metric("✅ Convertidos", convertidos)
        c3.metric("📈 Taxa de Conversão", taxa_conv)

        # ── Linha 2: Inteligência Comercial ──
        st.divider()
        c4, c5, c6 = st.columns(3)
        c4.metric("💰 Capital em Negociação", f"R$ {capital_neg:,.2f}")
        c5.metric("⚖️ Taxa de Decisores", taxa_decisores)
        c6.metric("💬 Taxa de Resposta", taxa_resposta)

        st.divider()

        # ── Gráfico de Distribuição por Status ──
        st.subheader("📊 Distribuição por Status de Contato")
        status_counts = (
            df_dash["Status de Contato"]
            .value_counts()
            .rename_axis("Status")
            .reset_index(name="Leads")
        )
        st.bar_chart(status_counts.set_index("Status"), use_container_width=True)

        st.divider()

        # ── Top 5 Status em tabela rápida ──
        col_t, col_s = st.columns([1, 1])
        with col_t:
            st.markdown("**Top Tipos de Negócio**")
            tipo_top = df_dash["Tipo de Negócio"].value_counts().head(5)
            st.dataframe(tipo_top.rename("Leads"), use_container_width=True)
        with col_s:
            st.markdown("**Funil de Status**")
            st.dataframe(status_counts.set_index("Status"), use_container_width=True)


# ───────────────────────────── MÓDULO: IMPORTAÇÃO ─────────────────────────────
elif menu == "📥 Importação":
    st.title("📥 Importação e Purificação Profunda")
    st.caption("Fluxo completo: Upload → Colunas → Renomear → Filtro Negativo → Smart Erase → Consolidação → Notion")

    # ── Estado inicial do módulo ──
    if "imp_df_original" not in st.session_state: st.session_state.imp_df_original = None
    if "imp_initial_count" not in st.session_state: st.session_state.imp_initial_count = 0

    # ══ 1. UPLOAD ══
    uploaded_file = st.file_uploader("Selecione o arquivo CSV", type=["csv"])
    if not uploaded_file:
        st.info("👆 Faça upload de um arquivo CSV para começar.")
        st.stop()

    try:
        raw = uploaded_file.getvalue()
        # Só lê do CSV se o estado da sessão estiver vazio (primeiro upload)
        if st.session_state.imp_df_original is None:
            try:   df = pd.read_csv(io.BytesIO(raw), encoding="utf-8",     dtype=str)
            except: df = pd.read_csv(io.BytesIO(raw), encoding="ISO-8859-1", dtype=str)
            st.session_state.imp_df_original = df.copy()
            st.session_state.imp_initial_count = len(df)
        else:
            df = st.session_state.imp_df_original

        c1, c2 = st.columns(2)
        c1.metric("Total de Leads", f"{st.session_state.imp_initial_count:,}")
        c2.metric("Colunas Atuais", len(df.columns))
        st.dataframe(df.head(3), use_container_width=True)
        
        if st.button("🔄 Reiniciar Importação (Recarregar CSV Bruto)"):
            st.session_state.imp_df_original = None
            st.rerun()
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}"); st.stop()

    st.divider()

    # 🧠 MAPEAMENTO INTELIGENTE
    if st.button("🧠 Aplicar Mapeamento Inteligente", use_container_width=True, help="Analisa o conteúdo, renomeia automaticamente e exclui colunas inúteis."):
        map_detectado = auto.identificar_colunas_por_conteudo(df)
        if map_detectado:
            # 1. Aplica o mapeamento e já limpa colunas obsoletas automaticamente
            df_clean = auto.limpar_colunas_obsoletas(df, map_detectado)
            
            # 2. Atualiza o estado da sessão com a base já purificada verticalmente
            st.session_state.imp_df_original = df_clean
            
            # 3. Feedback detalhado
            cols_id = list(set(map_detectado.values()))
            st.success(f"✅ Mapeamento concluído! {len(df_clean.columns)} colunas essenciais mantidas.")
            st.info(f"📋 Colunas identificadas: {', '.join(cols_id)}")
            time.sleep(2)
            st.rerun()
        else:
            st.warning("⚠️ Não foi possível identificar padrões automáticos nesta lista.")

    st.divider()
    
    # ══ INTELIGÊNCIA OUTSCRAPER (CASCATA) ══
    is_outscraper = st.checkbox("✨ Ativar Inteligência Outscraper (Cascata de E-mails)", value=False, key="imp_outscraper")
    if is_outscraper:
        st.caption("Aplica lógica de cascata: valida e-mails (Deliverable/Catch-all), phones e extrai decisores automaticamente.")

    # ══ 2. SELEÇÃO DE COLUNAS ══
    st.subheader("2 · Seleção de Colunas")
    all_cols = list(df.columns)
    selected_cols = st.multiselect("Colunas a manter", options=all_cols, default=all_cols, key="imp_sel_cols")
    if not selected_cols:
        st.warning("⚠️ Seleciona pelo menos uma coluna."); st.stop()
    df_filtered = df[selected_cols].copy()

    st.divider()

    # ══ 3. RENOMEAÇÃO DE COLUNAS ══
    st.subheader("3 · Renomeação de Colunas (Data Mapping)")
    st.markdown("Deixa em branco para manter o nome original.")
    rename_map = {}
    cols_per_row = 3
    for i in range(0, len(selected_cols), cols_per_row):
        row_cols = st.columns(cols_per_row)
        for j, col_name in enumerate(selected_cols[i:i+cols_per_row]):
            with row_cols[j]:
                new_name = st.text_input(f"**{col_name}**", value="", placeholder=col_name, key=f"imp_ren_{col_name}")
                if new_name.strip(): rename_map[col_name] = new_name.strip()
    if rename_map:
        df_filtered = df_filtered.rename(columns=rename_map)

    st.divider()

    # ══ 4. FILTRO NEGATIVO ══
    st.subheader("4 · Filtro Negativo (Exclusão por Palavra-Chave)")
    neg_input = st.text_input("Palavras proibidas (separadas por vírgula)", placeholder="ex: prefeitura, governo, teste", key="imp_neg")
    df_clean = df_filtered.copy()
    if neg_input.strip():
        keywords = [k.strip().lower() for k in neg_input.split(",") if k.strip()]
        pattern = "|".join([re.escape(k) for k in keywords])
        str_cols = df_clean.select_dtypes(include=["object"]).columns.tolist()
        if str_cols:
            mask = df_clean[str_cols].apply(lambda col: col.str.contains(pattern, case=False, na=False)).any(axis=1)
            removed = mask.sum()
            df_clean = df_clean[~mask]
            if removed > 0: st.success(f"🗑️ {removed:,} linhas removidas.")
            else: st.info("Nenhuma correspondência encontrada.")

    st.divider()

    # ══ 5. SMART ERASE ══
    st.subheader("5 · Smart Erase (Anulação Celular)")
    st.markdown("Anula **apenas a célula de contato** quando o status correspondente contém palavras inválidas.")
    invalid_status_input = st.text_input("Palavras de Status Inválido", placeholder="ex: UNKNOWN, Invalid, Bounced", key="imp_smart_kw")
    df_smart = df_clean.copy()
    smrt_cols = list(df_smart.columns)
    num_pairs = st.number_input("Quantos pares Contato ↔ Status analisar?", min_value=0, max_value=min(10, len(smrt_cols)//2) if len(smrt_cols)>=2 else 0, value=0, step=1, key="imp_smart_pairs")
    pairs_config = []
    if num_pairs > 0 and not invalid_status_input.strip():
        st.warning("⚠️ Define pelo menos uma palavra de status inválido acima.")
    for p in range(int(num_pairs)):
        st.markdown(f"**Par {p+1}**")
        cl, cr = st.columns(2)
        with cl:
            contact_col = st.selectbox(f"Coluna de Contato (par {p+1})", options=smrt_cols, index=0, key=f"imp_sc_{p}")
        suggested_idx = _find_status_candidate(contact_col, smrt_cols)
        with cr:
            status_col = st.selectbox(f"Coluna de Status (par {p+1})", options=smrt_cols, index=suggested_idx, key=f"imp_ss_{p}")
        if contact_col != status_col: pairs_config.append((contact_col, status_col))
        else: st.caption(f"⚠️ Par {p+1} ignorado — mesma coluna.")

    if pairs_config and invalid_status_input.strip():
        invalid_words = [w.strip().lower() for w in invalid_status_input.split(",") if w.strip()]
        invalid_pattern = "|".join([re.escape(w) for w in invalid_words])
        if st.button("⚡ Aplicar Smart Erase", key="imp_btn_smart", type="primary"):
            total_nullified = 0
            for c_col, s_col in pairs_config:
                if s_col in df_smart.columns and c_col in df_smart.columns:
                    mask = df_smart[s_col].astype(str).str.contains(invalid_pattern, case=False, na=False)
                    df_smart.loc[mask, c_col] = np.nan
                    total_nullified += mask.sum()
            st.session_state["imp_smart_df"] = df_smart.copy()
            st.session_state["imp_smart_n"] = total_nullified
            st.rerun()
    if st.session_state.get("imp_smart_df") is not None:
        df_smart = st.session_state["imp_smart_df"].copy()
        st.success(f"🧹 Smart Erase: **{st.session_state.get('imp_smart_n', 0):,}** células anuladas.")

    st.divider()

    # ══ 6. CONSOLIDAÇÃO DE CONTATOS (COALESCÊNCIA DE ELITE) ══
    st.subheader("6 · Consolidação de Contatos")
    st.markdown("Une múltiplas colunas de contato numa **coluna única** com validação por status positivo.")
    df_consolidated = df_smart.copy()
    num_groups = st.number_input("Quantos grupos consolidar?", min_value=0, max_value=10, value=0, step=1, key="imp_consol_groups")
    consol_rules = []
    for i in range(int(num_groups)):
        with st.expander(f"⚙️ Regra de Consolidação {i+1}", expanded=True):
            avail = list(df_consolidated.columns)
            rule_name = st.text_input("Nome da nova coluna", placeholder="ex: email, telefone", key=f"imp_cn_{i}")
            rule_sources = st.multiselect("Colunas a fundir (ordem de prioridade)", options=avail, key=f"imp_cs_{i}")
            rule_success_kw = st.text_input("Palavras-chave de Status Positivo", placeholder="ex: RECEIVING, Confirmed", key=f"imp_ck_{i}")
            status_map = {}
            if rule_sources and rule_success_kw.strip():
                st.markdown("**Emparelhamento Contato → Status:**")
                for j, src_col in enumerate(rule_sources):
                    pc = st.columns([1,1])
                    with pc[0]: st.text(f"📧 {src_col}")
                    with pc[1]:
                        suggested = _find_status_candidate(src_col, avail)
                        paired = st.selectbox(f"Status de `{src_col}`", options=["— Sem status —"] + avail, index=suggested+1, key=f"imp_csp_{i}_{j}", label_visibility="collapsed")
                        status_map[src_col] = paired if paired != "— Sem status —" else None
            rule_delete = st.checkbox("Apagar colunas de origem", value=True, key=f"imp_cd_{i}")
            apply_guillotine_rule = st.checkbox("🔪 Guilhotina — remover linhas sem contato após esta regra", value=False, key=f"imp_cg_{i}")
            if rule_name.strip() and len(rule_sources) >= 2:
                consol_rules.append({"name": rule_name.strip(), "sources": rule_sources, "success_kw": rule_success_kw.strip(), "status_map": status_map, "delete": rule_delete, "guillotine": apply_guillotine_rule})
                st.caption(f"✅ Regra válida: {len(rule_sources)} colunas → `{rule_name.strip()}`")
            elif rule_sources: st.caption("⚠️ Seleciona pelo menos 2 colunas.")

    if consol_rules:
        if st.button("🚀 Executar Consolidação", key="imp_btn_consol", type="primary"):
            for rule in consol_rules:
                sources, col_name = rule["sources"], rule["name"]
                success_kw, status_map = rule["success_kw"], rule["status_map"]
                for src in sources:
                    if src in df_consolidated.columns:
                        df_consolidated[src] = df_consolidated[src].replace(r"^\s*$", np.nan, regex=True)
                if success_kw:
                    success_words = [w.strip().lower() for w in success_kw.split(",") if w.strip()]
                    sp = "|".join([re.escape(w) for w in success_words])
                    filtered = []
                    for src in sources:
                        if src not in df_consolidated.columns: continue
                        sc = status_map.get(src)
                        if sc and sc in df_consolidated.columns:
                            is_valid = df_consolidated[sc].astype(str).str.contains(sp, case=False, na=False)
                            filtered.append(df_consolidated[src].where(is_valid, other=np.nan))
                        else:
                            filtered.append(df_consolidated[src].copy())
                    merged = filtered[0].copy()
                    for f in filtered[1:]: merged = merged.combine_first(f)
                else:
                    merged = df_consolidated[sources[0]].copy()
                    for src in sources[1:]:
                        if src in df_consolidated.columns: merged = merged.combine_first(df_consolidated[src])
                df_consolidated[col_name] = merged
                if rule["delete"]:
                    drop = [c for c in sources if c != col_name and c in df_consolidated.columns]
                    used_status = [v for v in status_map.values() if v and v in df_consolidated.columns and v != col_name]
                    df_consolidated.drop(columns=list(set(drop + used_status)), errors="ignore", inplace=True)
                if rule["guillotine"] and col_name in df_consolidated.columns:
                    before = len(df_consolidated)
                    df_consolidated = df_consolidated.dropna(subset=[col_name])
                    st.info(f"🔪 Guilhotina removeu {before - len(df_consolidated)} linhas sem '{col_name}'.")
            st.session_state["imp_consol_df"] = df_consolidated.copy()
            st.rerun()
    if st.session_state.get("imp_consol_df") is not None:
        df_consolidated = st.session_state["imp_consol_df"].copy()
        st.success(f"✅ Consolidação aplicada — {len(df_consolidated):,} leads restantes.")
        st.dataframe(df_consolidated.head(8), use_container_width=True)

    st.divider()

    # ══ 7. FINALIZAR PURIFICAÇÃO E LIMPAR LIXO ══
    st.subheader("7 · Finalizar Purificação")
    st.markdown("Executa a guilhotina (remoção de leads sem contato), limpeza de colunas extras e deduplicação Smart.")
    
    if st.button("🧹 Finalizar Purificação e Limpar Lixo", type="primary", use_container_width=True):
        with st.spinner("Limpando a base..."):
            # 1. Guilhotina
            df_guilhotina, removed_g = auto.executar_guilhotina(df_consolidated, is_outscraper=is_outscraper)
            
            # 2. Deduplicação Smart
            df_dedup, removed_d = auto.remover_duplicados_smart(df_guilhotina)
            
            # 3. Limpeza de Colunas (Opcional se quiser manter apenas as essenciais no CSV final)
            # No Notion já enviamos apenas as necessárias, mas o CSV baixado ficará mais limpo.
            essential_cols = ["Empresa", "Site Atual", "E-mail", "Telefone", "LinkedIn", "Instagram", "Decisor", "Tipo de Negócio", "Localização"]
            # Tenta mapear o que existe
            cols_to_keep = [c for c in df_dedup.columns if any(e.lower() in str(c).lower() for e in essential_cols)]
            if not cols_to_keep: cols_to_keep = list(df_dedup.columns) # Fallback
            
            df_final_clean = df_dedup[cols_to_keep].copy()
            
            st.session_state["imp_final_df"] = df_final_clean
            st.session_state["imp_removed_g"] = removed_g
            st.session_state["imp_removed_d"] = removed_d
            st.rerun()

    if st.session_state.get("imp_final_df") is not None:
        df_consolidated = st.session_state["imp_final_df"].copy()
        rg = st.session_state.get("imp_removed_g", 0)
        rd = st.session_state.get("imp_removed_d", 0)
        
        if rg > 0: st.warning(f"🗑️ {rg} leads sem contato válido foram movidos para a lixeira.")
        if rd > 0: st.success(f"✨ {rd} leads duplicados foram removidos para garantir uma base única.")
        st.info(f"📋 Base finalizada com {len(df_consolidated)} leads e {len(df_consolidated.columns)} colunas essenciais.")

    st.divider()

    # ══ 8. EXPORTAÇÃO E INTEGRAÇÃO COM NOTION ══
    st.subheader("8 · Exportação e Integração")
    df_final = df_consolidated.copy()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Leads Iniciais",    f"{st.session_state.imp_initial_count:,}")
    m2.metric("Leads Purificados", f"{len(df_final):,}")
    m3.metric("Taxa de Retenção",  f"{(len(df_final)/st.session_state.imp_initial_count*100):.1f}%" if st.session_state.imp_initial_count > 0 else "—")
    
    # ══ MÉTRICAS DE QUALIDADE ══
    if is_outscraper:
        # Usa a função de purificação final para contar quantos realmente têm contato válido
        df_valido = auto.processar_df_final(df_final, is_outscraper=True)
        m4.metric("🔥 Contatos Validados", len(df_valido))
    
    st.dataframe(df_final.head(10), use_container_width=True)

    col_exp, col_notion = st.columns(2)

    with col_exp:
        # Gera o DataFrame final processando a cascata para o CSV
        df_csv = auto.processar_df_final(df_final, is_outscraper=is_outscraper)
        csv_out = df_csv.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇️ Baixar CSV Purificado", data=csv_out, file_name="leads_purificados.csv", mime="text/csv", use_container_width=True)

    with col_notion:
        if st.button("🚀 Enviar para o Notion", type="primary", use_container_width=True, key="imp_send_notion"):
            if not auto.NOTION_TOKEN or not auto.DATABASE_ID:
                st.error("❌ Credenciais do Notion não configuradas. Verifique o arquivo .env")
                st.stop()
                
            # Prepara a base final (aplica cascata se necessário)
            df_notion = auto.processar_df_final(df_final, is_outscraper=is_outscraper)
            
            if df_notion.empty:
                st.warning("⚠️ Nenhum lead válido encontrado para envio.")
                st.info("💡 Isso geralmente acontece porque a **Inteligência Outscraper** está ativa e não encontrou e-mails/telefones validados (Status: DELIVERABLE). Tente desmarcar a opção de inteligência se quiser enviar a base bruta.")
                st.stop()

            progress_bar = st.progress(0)
            status_text  = st.empty()
            total, sucessos = len(df_notion), 0
            
            for i, (_, row) in enumerate(df_notion.iterrows()):
                empresa = row.get('Empresa', 'Lead')
                status_text.text(f"Integrando {i+1}/{total}: {empresa}")
                
                # Verifica duplicado
                page_id = auto.verificar_duplicado(row.get('Empresa'), row.get('Site Atual'), row.get('Localização'))
                
                if auto.enviar_notion_direto(row, page_id=page_id):
                    sucessos += 1
                
                progress_bar.progress((i + 1) / total)
                
            status_text.empty()
            st.success(f"🏁 Integração Concluída: {sucessos} leads processados com sucesso!")
            time.sleep(2)
            st.rerun()

    try:
        pass
    except Exception as e:
        st.error(f"Erro no processamento: {e}")


# ───────────────────────────── MÓDULO: DISPAROS ───────────────────────────────
elif menu == "🎯 Disparos":
    st.title("🎯 Prospecção Ativa (Multi-Canal)")
    
    # ── Inicialização de Scripts no Session State ──
    if "scripts_custom" not in st.session_state:
        st.session_state.scripts_custom = {
            "whatsapp": auto.obter_script_base("whatsapp"),
            "email": auto.obter_script_base("email"),
            "linkedin": auto.obter_script_base("linkedin"),
            "instagram": auto.obter_script_base("instagram")
        }

    tab_fila, tab_scripts = st.tabs(["🎯 Fila de Leads", "📜 Customizar Scripts"])

    # ── ABA: CUSTOMIZAR SCRIPTS ──
    with tab_scripts:
        st.subheader("📜 Modelos de Abordagem")
        st.caption("Use [Empresa] e [Diagnóstico] como variáveis automáticas.")
        
        st.session_state.scripts_custom["whatsapp"] = st.text_area("WhatsApp", st.session_state.scripts_custom["whatsapp"], height=100)
        st.session_state.scripts_custom["email"] = st.text_area("E-mail", st.session_state.scripts_custom["email"], height=150)
        st.session_state.scripts_custom["linkedin"] = st.text_area("LinkedIn", st.session_state.scripts_custom["linkedin"], height=100)
        st.session_state.scripts_custom["instagram"] = st.text_area("Instagram", st.session_state.scripts_custom["instagram"], height=100)
        
        if st.button("♻️ Resetar Padrões"):
            for k in st.session_state.scripts_custom:
                st.session_state.scripts_custom[k] = auto.obter_script_base(k)
            st.rerun()

    # ── ABA: FILA DE LEADS ──
    with tab_fila:
        if st.button("🔄 Atualizar Fila do Notion"):
            st.session_state.leads_prospeccao = auto.buscar_leads_notion()
            st.rerun()

        if "leads_prospeccao" not in st.session_state:
            st.session_state.leads_prospeccao = auto.buscar_leads_notion()

        leads = st.session_state.leads_prospeccao

        if not leads:
            st.info("🎉 Ninguém na fila! Todos os leads foram contactados ou a base está vazia.")
        else:
            st.write(f"Exibindo **{len(leads)}** leads prontos para abordagem.")
            
            for lead in leads:
                with st.container():
                    st.markdown(f"""
                        <div class="card">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span class="company-name">{lead['empresa']}</span>
                                <span class="status-badge">Aguardando Disparo</span>
                            </div>
                            <div style="margin-top: 10px;">
                                <a href="{lead['site']}" target="_blank" style="color: #4caf50; text-decoration: none;">🌐 {lead['site'] or 'Sem Site'}</a>
                            </div>
                            <div class="diagnostico">
                                <strong>Diagnóstico Gemini:</strong><br>
                                {lead['diagnostico'] or 'Análise pendente...'}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # ── Gerar links dinâmicos com scripts customizados ──
                    link_wa = auto.criar_link_whatsapp(lead.get('telefone'), lead.get('empresa'), lead.get('diagnostico'), st.session_state.scripts_custom.get("whatsapp"))
                    link_em = auto.gerar_link_email(lead.get('email'), lead.get('empresa'), lead.get('diagnostico'), st.session_state.scripts_custom.get("email"))
                    link_li = auto.gerar_link_linkedin(lead.get('linkedin'))
                    link_ig = auto.gerar_link_instagram(lead.get('instagram'))

                    # ── Determinar quais botões exibir ──
                    botoes_ativos = []
                    if link_wa: botoes_ativos.append(("wa", "📲 WhatsApp", link_wa))
                    if link_em: botoes_ativos.append(("em", "📧 E-mail", link_em))
                    if link_li: botoes_ativos.append(("li", "🔗 LinkedIn", link_li))
                    if link_ig: botoes_ativos.append(("ig", "📸 Instagram", link_ig))

                    # ── Renderizar Colunas de Disparo ──
                    if botoes_ativos:
                        cols = st.columns(len(botoes_ativos) + 1) # +1 para o botão de confirmação
                        for i, (tipo, label, url) in enumerate(botoes_ativos):
                            with cols[i]:
                                st.link_button(label, url, use_container_width=True)
                                if tipo in ["li", "ig"]:
                                    if st.button(f"📋 Script", key=f"scr_{tipo}_{lead.get('id')}", use_container_width=True):
                                        diag_limpo = str(lead.get('diagnostico')).replace('\n', ' ')[:200] if lead.get('diagnostico') else "análise técnica"
                                        # Mapeia as chaves curtas para as chaves do dicionário de scripts
                                        map_canais = {"li": "linkedin", "ig": "instagram"}
                                        canal_full = map_canais.get(tipo, tipo)
                                        
                                        script_base = st.session_state.scripts_custom.get(canal_full)
                                        if script_base:
                                            script_final = script_base.replace("[Empresa]", lead.get('empresa', 'Empresa')).replace("[Diagnóstico]", diag_limpo)
                                            st.info(script_final)
                                            st.code(script_final, language="text") # Facilita o copiar
                                        else:
                                            st.warning("⚠️ Script não encontrado.")

                        with cols[-1]:
                            with st.popover("✅ Confirmar", use_container_width=True):
                                st.markdown(f"**{lead.get('empresa')}**")
                                st.caption("Registre o canal utilizado antes de confirmar.")
                                escolha_meio = st.selectbox(
                                    "Por onde você contactou?",
                                    ["WhatsApp", "Instagram", "LinkedIn", "E-mail", "Ligação"],
                                    key=f"meio_{lead.get('id')}"
                                )
                                if st.button("📝 Registrar e Salvar", key=f"conf_{lead.get('id')}", type="primary", use_container_width=True):
                                    if auto.atualizar_status_disparo(lead.get('id'), meio_contato=escolha_meio):
                                        st.toast(f"🚀 {lead.get('empresa')} → '{escolha_meio}' registrado como 'Tentativa de contato'!")
                                        time.sleep(0.5)
                                        st.session_state.leads_prospeccao = [l for l in st.session_state.leads_prospeccao if l.get('id') != lead.get('id')]
                                        st.rerun()

                    else:
                        st.warning("⚠️ Nenhum canal de contato disponível para este lead.")
                        if st.button(f"✅ Marcar como Contactado (Manual)", key=f"man_{lead['id']}"):
                            if auto.atualizar_status_disparo(lead['id']):
                                st.session_state.leads_prospeccao = [l for l in st.session_state.leads_prospeccao if l['id'] != lead['id']]
                                st.rerun()

                st.divider()

# ───────────────────────────── MÓDULO: FOLLOW UP ─────────────────────────────
elif menu == "🔁 Follow Up":
    st.title("🔁 Esteira de Follow Up")
    st.caption("Acompanhamento inteligente com transições automáticas por prazo.")

    OPCOES_RESPOSTA = [
        "Aguardando...",
        "Respondeu",
        "Reunião agendada",
        "Aguardando retorno",
        "Não interessado",
        "Convertido",
    ]

    if st.button("🔄 Atualizar Esteira"):
        st.session_state.pop("leads_follow_up", None)

    # Sempre recarrega ao entrar na aba (invalida cache do session_state)
    if "leads_follow_up" not in st.session_state:
        with st.spinner("Carregando esteira do Notion..."):
            st.session_state.leads_follow_up = auto.buscar_leads_follow_up()

    leads_fu = st.session_state.leads_follow_up

    # ── Painel de Debug (expander oculto por padrão) ──
    with st.expander("🔍 Debug — Dados brutos da API", expanded=False):
        st.write(f"**Total retornado pelo Notion:** {len(leads_fu)} leads")
        if leads_fu:
            for i, l in enumerate(leads_fu):
                st.json({
                    "empresa":         l.get("empresa"),
                    "status":          l.get("status"),
                    "primeiro_contato":l.get("primeiro_contato"),
                })
        else:
            st.warning("A query retornou 0 resultados. Verifique se o lead tem status 'Tentativa de contato' ou 'Follow up' no Notion.")

    hoje = datetime.now().date()

    # ── Processa regras automáticas antes de renderizar ──
    leads_para_exibir = []
    auto_transicionados = 0

    for lead in leads_fu:
        status_atual = lead.get("status", "")
        pc_raw       = lead.get("primeiro_contato")

        if pc_raw:
            try:
                data_pc = datetime.strptime(pc_raw[:10], "%Y-%m-%d").date()
                dias_passados = (hoje - data_pc).days
            except Exception:
                dias_passados = 0
        else:
            dias_passados = 0

        # Regra 14 dias: Follow up → Arquivar automaticamente
        if status_atual == "Follow up" and dias_passados >= 14:
            if auto.atualizar_status_manual(lead["id"], "Arquivar"):
                auto_transicionados += 1
            continue  # Oculta da tela

        # Regra 5 dias: Tentativa de contato → Follow up automaticamente
        if status_atual == "Tentativa de contato" and dias_passados >= 5:
            if auto.atualizar_status_manual(lead["id"], "Follow up"):
                lead["status"] = "Follow up"  # Atualiza localmente para exibir correto
                auto_transicionados += 1

        leads_para_exibir.append((lead, dias_passados))

    if auto_transicionados > 0:
        st.info(f"⚙️ {auto_transicionados} lead(s) transição automática aplicada.")

    if not leads_para_exibir:
        st.success("✅ Nenhum lead pendente na esteira. Tudo em dia!")
    else:
        # Métricas rápidas
        tentativas = sum(1 for l, _ in leads_para_exibir if l["status"] == "Tentativa de contato")
        followups  = sum(1 for l, _ in leads_para_exibir if l["status"] == "Follow up")
        mc1, mc2 = st.columns(2)
        mc1.metric("Tentativas de Contato", tentativas)
        mc2.metric("Em Follow Up",          followups)
        st.divider()

        for lead, dias_passados in leads_para_exibir:
            status_cor = "#e67e22" if lead["status"] == "Follow up" else "#3498db"
            urgencia   = "🔴" if dias_passados >= 10 else ("🟡" if dias_passados >= 5 else "🟢")

            st.markdown(f"""
                <div style="background:#1e1e1e;padding:16px;border-radius:10px;
                            border-left:4px solid {status_cor};margin-bottom:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:1.1em;font-weight:bold;color:#fff;">{urgencia} {lead['empresa']}</span>
                        <span style="background:{status_cor};color:#fff;padding:3px 10px;
                               border-radius:4px;font-size:0.8em;">{lead['status']}</span>
                    </div>
                    <div style="color:#aaa;font-size:0.85em;margin-top:6px;">
                        📅 Primeiro contato: <b>{lead['primeiro_contato'] or 'Não registrado'}</b>
                        &nbsp;·&nbsp; ⏱ {dias_passados} dia(s) atrás
                        {f"&nbsp;·&nbsp; 📡 <b>Último contato via: {lead['meio_contato']}</b>" if lead.get('meio_contato') else ""}
                    </div>
                    <div style="color:#bbb;font-size:0.85em;margin-top:8px;font-style:italic;">
                        {lead['diagnostico'][:180] + '...' if lead['diagnostico'] and len(lead['diagnostico']) > 180 else lead['diagnostico'] or 'Diagnóstico não disponível.'}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            col_wa, col_sel = st.columns([1, 2])

            with col_wa:
                meio = lead.get("meio_contato", "")

                if meio == "WhatsApp":
                    if lead.get("link_wa"):
                        st.link_button("📲 WhatsApp", lead["link_wa"], use_container_width=True)
                    else:
                        st.button("📲 Sem Tel.", disabled=True, key=f"fu_notel_{lead['id']}")

                elif meio == "Instagram":
                    if lead.get("link_ig"):
                        st.link_button("📸 Instagram", lead["link_ig"], use_container_width=True)
                    else:
                        st.button("📸 Sem IG", disabled=True, key=f"fu_noig_{lead['id']}")

                elif meio == "LinkedIn":
                    if lead.get("link_li"):
                        st.link_button("👔 LinkedIn", lead["link_li"], use_container_width=True)
                    else:
                        st.button("👔 Sem LI", disabled=True, key=f"fu_noli_{lead['id']}")

                elif meio == "E-mail":
                    if lead.get("link_mail"):
                        st.link_button("📧 E-mail", lead["link_mail"], use_container_width=True)
                    else:
                        st.button("📧 Sem e-mail", disabled=True, key=f"fu_nomail_{lead['id']}")

                elif meio == "Ligação":
                    tel = lead.get("telefone", "")
                    if tel:
                        st.link_button("📞 Ligar", f"tel:{tel}", use_container_width=True)
                    else:
                        st.button("📞 Sem Tel.", disabled=True, key=f"fu_nocall_{lead['id']}")

                else:
                    # Fallback: sem meio registrado — exibe popover com todos os canais disponíveis
                    with st.popover("📡 Canais", use_container_width=True):
                        st.caption("Meio de contato não registrado. Escolha um canal:")
                        if lead.get("link_wa"):
                            st.link_button("📲 WhatsApp", lead["link_wa"], use_container_width=True)
                        if lead.get("link_ig"):
                            st.link_button("📸 Instagram", lead["link_ig"], use_container_width=True)
                        if lead.get("link_li"):
                            st.link_button("👔 LinkedIn", lead["link_li"], use_container_width=True)
                        if lead.get("link_mail"):
                            st.link_button("📧 E-mail", lead["link_mail"], use_container_width=True)

            with col_sel:

                escolha = st.selectbox(
                    "Atualizar status",
                    options=OPCOES_RESPOSTA,
                    index=0,
                    key=f"fu_sel_{lead['id']}",
                    label_visibility="collapsed",
                )
                if escolha != "Aguardando...":
                    if auto.atualizar_status_manual(lead["id"], escolha):
                        st.toast(f"✅ {lead['empresa']} → '{escolha}'")
                        time.sleep(0.4)
                        # Remove da lista local e recarrega
                        st.session_state.leads_follow_up = [
                            l for l in st.session_state.leads_follow_up
                            if l["id"] != lead["id"]
                        ]
                        st.rerun()
                    else:
                        st.error("Erro ao atualizar no Notion.")

            st.divider()

# ───────────────────────────── MÓDULO: MÉTRICAS ───────────────────────────────
elif menu == "📈 Métricas":
    st.title("📊 Análise de Performance")

    col_sync, _ = st.columns([1, 3])
    with col_sync:
        if st.button("🔄 Sincronizar Agora", help="Força nova leitura do Notion (limpa cache de 1h)"):
            auto.buscar_dados_completos.clear()
            st.toast("Cache limpo! Recarregando...")
            st.rerun()

    with st.spinner("Carregando dados..."):
        dados_raw = auto.buscar_dados_completos()

    if not dados_raw:
        st.warning("⚠️ Nenhum dado encontrado. Faça uma importação primeiro.")
    else:
        df_met = pd.DataFrame(dados_raw)

        # ── Linha de Gráficos Principais ──
        g1, g2 = st.columns(2)

        # ── Gráfico por Tipo de Negócio ──
        with g1:
            st.subheader("🏢 Leads por Tipo de Negócio")
            tipo_counts = (
                df_met["Tipo de Negócio"]
                .value_counts()
                .rename_axis("Tipo")
                .reset_index(name="Leads")
            )
            st.bar_chart(tipo_counts.set_index("Tipo"), use_container_width=True)

        # ── Gráfico por Status ──
        with g2:
            st.subheader("📊 Leads por Status")
            status_counts = (
                df_met["Status de Contato"]
                .value_counts()
                .rename_axis("Status")
                .reset_index(name="Leads")
            )
            st.bar_chart(status_counts.set_index("Status"), use_container_width=True)

        st.divider()

        # ── Inteligência de Objeções e Canais ──
        g3, g4 = st.columns(2)

        with g3:
            st.subheader("🛡️ Gráfico de Objeções (Motivo)")
            # Filtrar motivos vazios para o gráfico ser limpo
            df_motivo = df_met[df_met["Motivo"] != ""].copy()
            if not df_motivo.empty:
                motivo_counts = df_motivo["Motivo"].value_counts()
                st.bar_chart(motivo_counts, use_container_width=True)
            else:
                st.caption("Sem dados de motivos registrados.")

        with g4:
            st.subheader("📡 Canais de Prospecção")
            df_canal = df_met[df_met["Meio de Contato"] != ""].copy()
            if not df_canal.empty:
                canal_counts = df_canal["Meio de Contato"].value_counts()
                st.bar_chart(canal_counts, use_container_width=True)
            else:
                st.caption("Sem dados de canais registrados.")

# ───────────────────────────── MÓDULO: EVOLUTION HISTORY ─────────────────────
elif menu == "🧬 Evolution History":
    st.title("🧬 NXT OS — Evolução Progressiva")
    st.caption("Acompanhe o histórico de alterações, marcos e o crescimento do sistema.")
    
    path_changelog = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CHANGELOG.md")
    
    if os.path.exists(path_changelog):
        with open(path_changelog, "r", encoding="utf-8") as f:
            content = f.read()
        st.markdown(content)
    else:
        st.warning("⚠️ Arquivo CHANGELOG.md não encontrado no diretório raiz.")
        st.info("O sistema está atualmente na versão v1.4.0 Beta.")

st.sidebar.divider()
st.sidebar.caption("NXT - Build. Learn. Evolve.")
