import streamlit as st
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
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/rocket.png", width=60)
    st.title("NXT OS")
    st.caption("v1.0 · Senior Edition")
    st.divider()
    menu = st.radio(
        "Menu Principal",
        ["🏠 Dashboard", "📥 Importação", "🎯 Disparos", "🔁 Follow Up", "📊 Métricas"],
        index=1
    )

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
if menu == "🏠 Dashboard":
    st.title("🚀 NXT OS — Command Center")

    with st.spinner("Sincronizando dados do Notion..."):
        dados_raw = auto.buscar_dados_completos()

    if not dados_raw:
        st.warning("⚠️ Sem dados. Verifique as credenciais do Notion ou faça uma importação primeiro.")
    else:
        df_dash = pd.DataFrame(dados_raw)

        total       = len(df_dash)
        convertidos = int((df_dash["Status de Contato"] == "Convertido").sum())
        taxa        = f"{(convertidos / total * 100):.1f}%" if total > 0 else "0%"

        c1, c2, c3 = st.columns(3)
        c1.metric("📊 Total de Leads",    total)
        c2.metric("✅ Convertidos",        convertidos)
        c3.metric("📈 Taxa de Conversão", taxa)

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
        try:   df = pd.read_csv(io.BytesIO(raw), encoding="utf-8",     dtype=str)
        except: df = pd.read_csv(io.BytesIO(raw), encoding="ISO-8859-1", dtype=str)
        st.session_state.imp_df_original = df.copy()
        st.session_state.imp_initial_count = len(df)
        c1, c2 = st.columns(2)
        c1.metric("Total de Leads", f"{len(df):,}")
        c2.metric("Colunas Detetadas", len(df.columns))
        st.dataframe(df.head(3), use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}"); st.stop()

    st.divider()

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

    # ══ 7. EXPORTAÇÃO E INTEGRAÇÃO COM NOTION ══
    st.subheader("7 · Exportação e Integração")
    df_final = df_consolidated.copy()
    m1, m2, m3 = st.columns(3)
    m1.metric("Leads Iniciais",    f"{st.session_state.imp_initial_count:,}")
    m2.metric("Leads Purificados", f"{len(df_final):,}")
    m3.metric("Taxa de Retenção",  f"{(len(df_final)/st.session_state.imp_initial_count*100):.1f}%" if st.session_state.imp_initial_count > 0 else "—")
    st.dataframe(df_final.head(10), use_container_width=True)

    col_exp, col_notion = st.columns(2)

    with col_exp:
        csv_out = df_final.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇️ Baixar CSV Purificado", data=csv_out, file_name="leads_purificados.csv", mime="text/csv", use_container_width=True)

    with col_notion:
        if st.button("🚀 Enviar para o Notion", type="primary", use_container_width=True, key="imp_send_notion"):
            progress_bar = st.progress(0)
            status_text  = st.empty()
            total, sucessos = len(df_final), 0
            for i, (_, row) in enumerate(df_final.iterrows()):
                empresa = auto.buscar_dado(row, 'empresa')
                site    = auto.buscar_dado(row, 'site')
                status_text.text(f"Integrando {i+1}/{total}: {empresa or 'Lead'}")
                lead_data = {
                    'empresa':       empresa,
                    'site':          site,
                    'telefone':      auto.buscar_dado(row, 'telefone'),
                    'email':         auto.buscar_dado(row, 'email'),
                    'status':        auto.buscar_dado(row, 'status'),
                    'tipo_negocio':  auto.categorizar_negocio(auto.buscar_dado(row, 'tipo_negocio')),
                    'localizacao':   auto.buscar_dado(row, 'localizacao'),
                    'decisor':       auto.buscar_dado(row, 'decisor'),
                    'avaliacao':     auto.buscar_dado(row, 'avaliacao'),
                    'qtd_avaliacoes':auto.buscar_dado(row, 'qtd_avaliacoes'),
                    'rid':           auto.gerar_rid(site, empresa),
                    'disparo':       auto.buscar_dado(row, 'disparo'),
                    'motivo':        auto.buscar_dado(row, 'motivo'),
                    'meio_contato':  auto.buscar_dado(row, 'meio_contato'),
                    'observacoes':   auto.buscar_dado(row, 'observacoes'),
                    'primeiro_contato': auto.buscar_dado(row, 'primeiro_contato'),
                    'data_resposta': auto.buscar_dado(row, 'data_resposta'),
                }
                page_id = auto.verificar_duplicado(lead_data['empresa'], lead_data['site'], lead_data['localizacao'])
                if auto.enviar_notion(lead_data, page_id=page_id):
                    sucessos += 1
                progress_bar.progress((i + 1) / total)
            status_text.empty()
            st.success(f"🏁 Concluído! {sucessos}/{total} leads enviados ao Notion.")

    try:
        pass
    except Exception as e:
        st.error(f"Erro no processamento: {e}")


# ───────────────────────────── MÓDULO: DISPAROS ───────────────────────────────
elif menu == "🎯 Disparos":
    st.title("🎯 Prospecção Ativa (Disparos)")
    st.caption("Fila de leads aguardando primeiro contato via WhatsApp.")
    
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
                
                col_btn1, col_btn2, col_btn3 = st.columns([1.2, 1.2, 1.6])
                
                with col_btn1:
                    if lead['link_wa']:
                        st.link_button("📲 Abrir WhatsApp", lead['link_wa'], help="Abre o WhatsApp Web/App em uma nova aba.")
                    else:
                        st.button("📲 Sem Telefone", disabled=True, key=f"no_tel_{lead['id']}")

                with col_btn2:
                    if st.button(f"✅ Confirmar Disparo", key=f"conf_{lead['id']}", help="Confirma o envio e atualiza o Notion."):
                        if auto.atualizar_status_disparo(lead['id']):
                            st.toast(f"🚀 {lead['empresa']} marcado como 'Tentativa de contato'!")
                            time.sleep(0.5)
                            st.session_state.leads_prospeccao = [l for l in st.session_state.leads_prospeccao if l['id'] != lead['id']]
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar no Notion. Verifique os logs.")
                
                with col_btn3:
                    if st.button(f"❌ Pular", key=f"skip_{lead['id']}"):
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
                    </div>
                    <div style="color:#bbb;font-size:0.85em;margin-top:8px;font-style:italic;">
                        {lead['diagnostico'][:180] + '...' if lead['diagnostico'] and len(lead['diagnostico']) > 180 else lead['diagnostico'] or 'Diagnóstico não disponível.'}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            col_wa, col_sel = st.columns([1, 2])

            with col_wa:
                if lead["link_wa"]:
                    st.link_button("📲 WhatsApp", lead["link_wa"],
                                   help="Abre o WhatsApp Web/App.")
                else:
                    st.button("📲 Sem Tel.", disabled=True, key=f"fu_notel_{lead['id']}")

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
elif menu == "📊 Métricas":
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

        # ── Tabela Interativa ──
        st.subheader("📄 Tabela de Leads")
        st.dataframe(
            df_met,
            use_container_width=True,
            column_config={
                "Empresa":           st.column_config.TextColumn("Empresa"),
                "Status de Contato": st.column_config.TextColumn("Status"),
                "Tipo de Negócio":  st.column_config.TextColumn("Tipo de Negócio"),
                "Avaliação":        st.column_config.NumberColumn(
                    "Avaliação ★",
                    format="%.1f ★",
                    min_value=0,
                    max_value=5,
                ),
            },
            hide_index=True,
        )

        st.divider()

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
            st.bar_chart(
                tipo_counts.set_index("Tipo"),
                use_container_width=True,
            )

        # ── Gráfico por Status ──
        with g2:
            st.subheader("📊 Leads por Status")
            status_counts = (
                df_met["Status de Contato"]
                .value_counts()
                .rename_axis("Status")
                .reset_index(name="Leads")
            )
            st.bar_chart(
                status_counts.set_index("Status"),
                use_container_width=True,
            )

        st.divider()

        # ── Avaliação Média por Tipo ──
        st.subheader("⭐ Avaliação Média por Segmento")
        avg_rating = (
            df_met.groupby("Tipo de Negócio")["Avaliação"]
            .mean()
            .sort_values(ascending=False)
            .round(2)
            .rename("Média")
        )
        st.bar_chart(avg_rating, use_container_width=True)

st.sidebar.divider()
st.sidebar.caption("NXT OS — Powered by Gemini 2.0 Flash")
