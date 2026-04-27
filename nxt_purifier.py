"""
NXT Purifier — MVP
Sistema interno para higienização de listas de leads B2B (.csv).
Executa localmente em ambiente Windows via Streamlit.

Uso:
    streamlit run nxt_purifier.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import automacao_nxt as auto

# ───────────────────────────── Configuração da Página ─────────────────────────
st.set_page_config(
    page_title="NXT Purifier",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ───────────────────────────── Header ─────────────────────────────────────────
st.title("🧹 NXT Purifier")
st.caption("Higienização rápida de listas de leads B2B — Upload → Filtrar → Renomear → Limpar → Smart Erase → Consolidar → Exportar")
st.divider()

# ───────────────────────────── Estado Inicial ─────────────────────────────────
if "df_original" not in st.session_state:
    st.session_state.df_original = None
if "df_work" not in st.session_state:
    st.session_state.df_work = None
if "initial_count" not in st.session_state:
    st.session_state.initial_count = 0


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MÓDULO DE UPLOAD ROBUSTO
# ═══════════════════════════════════════════════════════════════════════════════
st.subheader("1 · Upload do Ficheiro CSV")
st.markdown("Arrasta ou seleciona o ficheiro `.csv` com os leads. O sistema tenta automaticamente detetar a codificação correta.")

uploaded_file = st.file_uploader(
    "Seleciona o ficheiro CSV",
    type=["csv"],
    help="Formatos aceites: .csv — Codificações suportadas: UTF-8, ISO-8859-1 / Latin-1",
)

if uploaded_file is not None:
    # ── Leitura com fallback de encoding ──
    try:
        raw_bytes = uploaded_file.getvalue()

        # Tentativa 1 — UTF-8
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8", dtype=str)
            encoding_used = "UTF-8"
        except (UnicodeDecodeError, pd.errors.ParserError):
            # Tentativa 2 — ISO-8859-1 / Latin-1 (comum em ficheiros Excel/Windows)
            try:
                df = pd.read_csv(io.BytesIO(raw_bytes), encoding="ISO-8859-1", dtype=str)
                encoding_used = "ISO-8859-1"
            except Exception as e:
                st.error(f"❌ Não foi possível ler o ficheiro. Erro: {e}")
                st.stop()

        # Guardar no session_state
        st.session_state.df_original = df.copy()
        st.session_state.df_work = df.copy()
        st.session_state.initial_count = len(df)

        # Métricas rápidas
        col_info1, col_info2, col_info3 = st.columns(3)
        col_info1.metric("Total de Leads", f"{len(df):,}")
        col_info2.metric("Colunas Detetadas", len(df.columns))
        col_info3.metric("Codificação Utilizada", encoding_used)

        st.markdown("**Pré-visualização (3 primeiras linhas):**")
        st.dataframe(df.head(3), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Erro inesperado ao processar o ficheiro: {e}")
        st.stop()
else:
    st.info("👆 Faz upload de um ficheiro CSV para começar.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SELETOR DE COLUNAS (FILTRO VERTICAL)
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("2 · Seleção de Colunas")
st.markdown("Remove as colunas irrelevantes. Apenas as colunas selecionadas serão mantidas no ficheiro final.")

all_columns = list(st.session_state.df_work.columns)

selected_columns = st.multiselect(
    "Colunas a manter",
    options=all_columns,
    default=all_columns,
    help="Desmarca as colunas que não são necessárias para o CRM.",
)

if not selected_columns:
    st.warning("⚠️ Seleciona pelo menos uma coluna para continuar.")
    st.stop()

# Aplicar filtro de colunas
df_filtered = st.session_state.df_work[selected_columns].copy()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EDITOR DE COLUNAS (DATA MAPPING)
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("3 · Renomeação de Colunas (Data Mapping)")
st.markdown("Renomeia cada coluna para o formato esperado pelo CRM. Deixa em branco para manter o nome original.")

rename_map = {}
# Gerar inputs lado a lado — 3 colunas por linha
cols_per_row = 3
for i in range(0, len(selected_columns), cols_per_row):
    row_cols = st.columns(cols_per_row)
    for j, col_name in enumerate(selected_columns[i : i + cols_per_row]):
        with row_cols[j]:
            new_name = st.text_input(
                f"**{col_name}**",
                value="",
                placeholder=col_name,
                key=f"rename_{col_name}",
                help=f"Novo nome para '{col_name}'. Deixa vazio para manter.",
            )
            if new_name.strip():
                rename_map[col_name] = new_name.strip()

# Aplicar renomeação
if rename_map:
    df_filtered = df_filtered.rename(columns=rename_map)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FILTRO NEGATIVO (LIMPEZA POR PALAVRA-CHAVE)
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("4 · Filtro Negativo (Exclusão por Palavra-Chave)")
st.markdown(
    "Insere palavras proibidas separadas por **vírgula**. "
    "Qualquer linha que contenha uma dessas palavras (em qualquer coluna de texto) será **removida**."
)

negative_keywords_input = st.text_input(
    "Palavras proibidas",
    value="",
    placeholder="ex: prefeitura, governo, escola, inativo, teste",
    help="Pesquisa case-insensitive em todas as colunas de texto.",
)

df_clean = df_filtered.copy()
removed_count = 0

if negative_keywords_input.strip():
    keywords = [kw.strip().lower() for kw in negative_keywords_input.split(",") if kw.strip()]

    if keywords:
        # Identificar colunas do tipo string/object
        str_cols = df_clean.select_dtypes(include=["object"]).columns.tolist()

        if str_cols:
            # Construir máscara: True se a linha contém alguma das palavras proibidas
            pattern = "|".join([k.replace("|", r"\|") for k in keywords])  # escape seguro
            mask = df_clean[str_cols].apply(
                lambda col: col.str.contains(pattern, case=False, na=False)
            ).any(axis=1)

            removed_count = mask.sum()
            df_clean = df_clean[~mask]

            if removed_count > 0:
                st.success(f"🗑️ {removed_count:,} linhas removidas com base nas palavras proibidas.")
            else:
                st.info("Nenhuma correspondência encontrada — 0 linhas removidas.")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SMART ERASE — ANULAÇÃO CELULAR CONDICIONAL
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("5 · Smart Erase (Anulação Celular)")
st.markdown(
    "Anula **apenas a célula de contato** quando o status correspondente contém palavras inválidas. "
    "A linha permanece intacta — só o dado de contato é limpo."
)

# ── 5a. Palavras de status inválido ──
invalid_status_input = st.text_input(
    "Palavras de Status Inválido",
    value="",
    placeholder="ex: UNKNOWN, Invalid, Bounced, Unsubscribed, Do Not Contact",
    key="smart_erase_keywords",
    help="Palavras separadas por vírgula. Se a coluna de status contiver alguma destas, a célula de contato é anulada.",
)


def _find_status_candidate(contact_col: str, all_cols: list[str]) -> int:
    """Motor de auto-sugestão: procura a coluna de status mais provável para
    uma dada coluna de contato, usando correspondência parcial no nome.

    Estratégia de procura (por prioridade):
    1. Extrai o prefixo numérico do contato (ex: '1' de 'email_1') e procura
       colunas que contenham esse prefixo E 'status'.
    2. Extrai a raiz da palavra (ex: 'email' de 'email_1') e procura colunas
       que contenham essa raiz E 'status'.
    3. Procura qualquer coluna com 'status' no nome.
    """
    contact_lower = contact_col.lower()

    # Extrair sufixo numérico (ex: email_1 → '1', email_01 → '01')
    num_match = re.search(r"(\d+)", contact_lower)
    suffix = num_match.group(1) if num_match else None

    # Extrair raiz (tudo antes do primeiro dígito ou underscore+dígito)
    root = re.split(r"[_\s]*\d", contact_lower)[0].strip("_ ")

    for priority_fn in [
        # Prioridade 1: raiz + sufixo + status  (ex: email_1 → email_1_status)
        lambda c: (suffix and suffix in c and root and root in c and "status" in c),
        # Prioridade 2: sufixo + status  (ex: email_1 → contact_1_status)
        lambda c: (suffix and suffix in c and "status" in c),
        # Prioridade 3: raiz + status  (ex: email → email_status)
        lambda c: (root and root in c and "status" in c),
    ]:
        for idx, col in enumerate(all_cols):
            col_lower = col.lower()
            if col_lower == contact_lower:
                continue
            if priority_fn(col_lower):
                return idx

    return 0  # fallback: primeiro da lista


# ── 5b. Motor de auto-correlação ──
df_smart = df_clean.copy()
smrt_cols = list(df_smart.columns)

num_pairs = st.number_input(
    "Quantos pares Contato ↔ Status queres analisar?",
    min_value=0,
    max_value=min(10, len(smrt_cols) // 2) if len(smrt_cols) >= 2 else 0,
    value=0,
    step=1,
    key="smart_erase_pairs",
    help="Define 0 para saltar este passo.",
)

pairs_config: list[tuple[str, str]] = []

if num_pairs > 0 and not invalid_status_input.strip():
    st.warning("⚠️ Define pelo menos uma palavra de status inválido acima para ativar a anulação.")

for p in range(int(num_pairs)):
    st.markdown(f"**Par {p + 1}**")
    col_left, col_right = st.columns(2)

    with col_left:
        contact_col = st.selectbox(
            f"Coluna de Contato (par {p + 1})",
            options=smrt_cols,
            index=0,
            key=f"smart_contact_{p}",
            help="Coluna cujo valor será anulado se o status for inválido.",
        )

    # Auto-sugestão do status
    suggested_idx = _find_status_candidate(contact_col, smrt_cols)

    with col_right:
        status_col = st.selectbox(
            f"Coluna de Status (par {p + 1})",
            options=smrt_cols,
            index=suggested_idx,
            key=f"smart_status_{p}",
            help="Coluna de status associada. O sistema sugere automaticamente — podes alterar.",
        )

    if contact_col != status_col:
        pairs_config.append((contact_col, status_col))
    else:
        st.caption(f"⚠️ Par {p + 1} ignorado — contato e status apontam para a mesma coluna.")

# ── 5c. Execução da anulação ──
smrt_nullified_total = 0

if pairs_config and invalid_status_input.strip():
    invalid_words = [w.strip().lower() for w in invalid_status_input.split(",") if w.strip()]
    invalid_pattern = "|".join([re.escape(w) for w in invalid_words])

    if st.button("⚡ Aplicar Regras de Anulação", key="btn_smart_erase", type="primary"):
        for contact_col, status_col in pairs_config:
            if status_col in df_smart.columns and contact_col in df_smart.columns:
                mask = df_smart[status_col].astype(str).str.contains(
                    invalid_pattern, case=False, na=False
                )
                count = mask.sum()
                df_smart.loc[mask, contact_col] = np.nan
                smrt_nullified_total += count

        st.session_state["_smart_erase_applied"] = True
        st.session_state["_smart_erase_df"] = df_smart.copy()
        st.session_state["_smart_erase_nullified"] = smrt_nullified_total
        st.rerun()

# Recuperar estado após rerun
if st.session_state.get("_smart_erase_applied"):
    df_smart = st.session_state["_smart_erase_df"].copy()
    smrt_nullified_total = st.session_state.get("_smart_erase_nullified", 0)
    st.success(f"🧹 Smart Erase concluído — **{smrt_nullified_total:,}** células de contato anuladas.")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. CONSOLIDAÇÃO DE CONTATOS — COALESCÊNCIA DE ELITE
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("6 · Consolidação de Contatos")
st.markdown(
    "Une múltiplas colunas de contato numa **coluna principal única** usando coalescência "
    "validada por status (`combine_first`). Apenas contatos com **status positivo** são aceites. "
    "Podes criar vários grupos (Email, Telefone, WhatsApp, etc.) no mesmo passo."
)

df_consolidated = df_smart.copy()

# ── 6a. Quantidade de grupos ──
num_groups = st.number_input(
    "Quantos grupos de dados deseja consolidar?",
    min_value=0,
    max_value=10,
    value=0,
    step=1,
    key="consol_num_groups",
    help="Cada grupo funde várias colunas numa só (ex: email_1 + email_2 → email). Define 0 para saltar.",
)

# ── 6b. Recolha dinâmica de regras via UI ──
consol_rules_valid = []

for i in range(int(num_groups)):
    with st.expander(f"⚙️ Regra de Consolidação {i + 1}", expanded=True):
        consol_cols_available = list(df_consolidated.columns)

        rule_name = st.text_input(
            "Nome da nova coluna consolidada",
            value="",
            placeholder="ex: email, telefone, whatsapp, website",
            key=f"consol_name_{i}",
            help="Nome final da coluna unificada.",
        )

        rule_sources = st.multiselect(
            "Colunas de contato a fundir (por ordem de prioridade)",
            options=consol_cols_available,
            default=[],
            key=f"consol_cols_{i}",
            help="A primeira coluna tem prioridade máxima. As seguintes preenchem apenas onde a anterior é vazia.",
        )

        # ── Palavras-chave de sucesso (critério de validação) ──
        rule_success_kw = st.text_input(
            "Palavras-chave de Sucesso (Status Positivo)",
            value="",
            placeholder="ex: RECEIVING, Confirmed, Valido, Active",
            key=f"consol_success_{i}",
            help="Separadas por vírgula. Se definidas, apenas contatos cujo status contenha uma destas palavras serão aceites na coalescência.",
        )

        # ── Emparelhamento Contato ↔ Status (por coluna fonte) ──
        rule_status_map: dict[str, str | None] = {}

        if rule_sources and rule_success_kw.strip():
            st.markdown("**Emparelhamento Contato → Status:**")
            st.caption("Para cada coluna de contato, indica qual coluna contém o status correspondente. O sistema sugere automaticamente.")

            for j, src_col in enumerate(rule_sources):
                pair_cols = st.columns([1, 1])
                with pair_cols[0]:
                    st.text(f"📧 {src_col}")
                with pair_cols[1]:
                    suggested_idx = _find_status_candidate(src_col, consol_cols_available)
                    paired_status = st.selectbox(
                        f"Status de `{src_col}`",
                        options=["— Sem coluna de status —"] + consol_cols_available,
                        index=suggested_idx + 1,  # +1 por causa da opção vazia
                        key=f"consol_status_{i}_{j}",
                        label_visibility="collapsed",
                    )
                    if paired_status != "— Sem coluna de status —":
                        rule_status_map[src_col] = paired_status
                    else:
                        rule_status_map[src_col] = None

        rule_delete = st.checkbox(
            "Apagar colunas de origem após consolidação",
            value=True,
            key=f"consol_del_{i}",
            help="Remove as colunas de contato e status originais, mantendo apenas a coluna consolidada.",
        )

        # Validação inline
        if rule_name.strip() and len(rule_sources) >= 2:
            consol_rules_valid.append({
                "name": rule_name.strip(),
                "sources": rule_sources,
                "delete_originals": rule_delete,
                "success_keywords": rule_success_kw.strip(),
                "status_map": rule_status_map,
            })
            mode = "com validação de status" if rule_success_kw.strip() else "sem filtro de status"
            st.caption(f"✅ Regra válida ({mode}): `{rule_sources[0]}` + {len(rule_sources) - 1} coluna(s) → `{rule_name.strip()}`")
        elif rule_sources and len(rule_sources) < 2:
            st.caption("⚠️ Seleciona pelo menos 2 colunas para fundir.")
        elif not rule_name.strip() and rule_sources:
            st.caption("⚠️ Define um nome para a coluna consolidada.")

# ── 6c. Guilhotina global ──
apply_guillotine = False
guillotine_col = None

if consol_rules_valid:
    st.markdown("---")
    apply_guillotine = st.checkbox(
        "🔪 Guilhotina — remover linhas sem contato após consolidação",
        value=False,
        key="consol_guillotine",
        help="Remove linhas onde a coluna principal consolidada ficou vazia (NaN) após a fusão.",
    )
    if apply_guillotine:
        guillotine_options = [r["name"] for r in consol_rules_valid]
        guillotine_col = st.selectbox(
            "Coluna principal para a guilhotina",
            options=guillotine_options,
            index=0,
            key="consol_guillotine_col",
            help="A guilhotina remove linhas apenas com base nesta coluna.",
        )
    
    st.markdown("---")
    pre_validate_wa = st.checkbox(
        "🛡️ Pré-validar WhatsApp (Evolution API)",
        value=False,
        key="consol_pre_validate_wa",
        help="Verifica via API se o número existe no WhatsApp. Descarta o lead se for inválido. (Requer conexão estável)",
    )

# ── 6d. Execução em massa (Coalescência de Elite) ──
if consol_rules_valid:
    if st.button("🚀 Executar Consolidação em Massa", key="btn_consolidate", type="primary"):
        log_messages = []
        total_promoted = 0
        total_discarded_cells = 0

        for rule in consol_rules_valid:
            col_name = rule["name"]
            sources = rule["sources"]
            success_kw_raw = rule["success_keywords"]
            status_map = rule["status_map"]

            # Limpar falsos espaços em branco → NaN
            for src in sources:
                if src in df_consolidated.columns:
                    df_consolidated[src] = df_consolidated[src].replace(
                        r"^\s*$", np.nan, regex=True
                    )

            # ── Preparar séries filtradas por status (se keywords definidas) ──
            if success_kw_raw:
                success_words = [w.strip().lower() for w in success_kw_raw.split(",") if w.strip()]
                success_pattern = "|".join([re.escape(w) for w in success_words])

                filtered_sources = []
                rule_promoted = 0
                rule_discarded = 0

                for src in sources:
                    if src not in df_consolidated.columns:
                        continue

                    status_col = status_map.get(src)

                    if status_col and status_col in df_consolidated.columns:
                        # Verificar quais linhas têm status positivo
                        is_valid = df_consolidated[status_col].astype(str).str.contains(
                            success_pattern, case=False, na=False
                        )
                        # Criar série filtrada: manter valor apenas se status positivo
                        clean_series = df_consolidated[src].where(is_valid, other=np.nan)

                        accepted = is_valid.sum()
                        rejected = (~is_valid & df_consolidated[src].notna()).sum()
                        rule_promoted += int(accepted)
                        rule_discarded += int(rejected)
                    else:
                        # Sem coluna de status emparelhada → aceitar todos os não-nulos
                        clean_series = df_consolidated[src].copy()
                        rule_promoted += int(clean_series.notna().sum())

                    filtered_sources.append(clean_series)

                # Coalescência sobre dados filtrados
                consolidated_series = filtered_sources[0].copy()
                for flt_src in filtered_sources[1:]:
                    consolidated_series = consolidated_series.combine_first(flt_src)

                total_promoted += rule_promoted
                total_discarded_cells += rule_discarded

                filled = consolidated_series.notna().sum()
                log_messages.append(
                    f"✅ `{col_name}` — {len(sources)} colunas fundidas | "
                    f"**{filled:,}** contactos válidos | "
                    f"🏆 {rule_promoted:,} promovidos | "
                    f"🚫 {rule_discarded:,} rejeitados por status"
                )
            else:
                # Sem validação de status → coalescência simples
                consolidated_series = df_consolidated[sources[0]].copy()
                for src in sources[1:]:
                    if src in df_consolidated.columns:
                        consolidated_series = consolidated_series.combine_first(
                            df_consolidated[src]
                        )
                filled = consolidated_series.notna().sum()
                log_messages.append(
                    f"✅ `{col_name}` — {len(sources)} colunas fundidas, "
                    f"{filled:,} valores preenchidos (sem filtro de status)"
                )

            df_consolidated[col_name] = consolidated_series

            # Apagar colunas de origem (se pedido)
            if rule["delete_originals"]:
                cols_to_drop = [c for c in sources if c != col_name and c in df_consolidated.columns]
                # Também apagar colunas de status usadas no emparelhamento
                if status_map:
                    status_cols_used = [v for v in status_map.values() if v and v in df_consolidated.columns and v != col_name]
                    cols_to_drop.extend(status_cols_used)
                cols_to_drop = list(set(cols_to_drop))
                df_consolidated = df_consolidated.drop(columns=cols_to_drop, errors="ignore")

        # Reordenar: colunas consolidadas no início
        new_cols = [r["name"] for r in consol_rules_valid if r["name"] in df_consolidated.columns]
        remaining = [c for c in df_consolidated.columns if c not in new_cols]
        df_consolidated = df_consolidated[new_cols + remaining]

        pre_guillotine = len(df_consolidated)

        # Guilhotina
        if apply_guillotine and guillotine_col and guillotine_col in df_consolidated.columns:
            df_consolidated = df_consolidated.dropna(subset=[guillotine_col])

        post_guillotine = len(df_consolidated)

        # Validação de WhatsApp (Evolution API)
        total_wa_invalid = 0
        if pre_validate_wa:
            with st.spinner("🛡️ Validando contas de WhatsApp via Evolution API..."):
                # Procura coluna de telefone para validar
                col_tel = next((c for c in df_consolidated.columns if "tele" in c.lower() or "phone" in c.lower() or "whats" in c.lower()), None)
                if col_tel:
                    initial_len = len(df_consolidated)
                    # Aplica a validação linha a linha (o cache do Streamlit ajuda aqui)
                    df_consolidated = df_consolidated[df_consolidated[col_tel].apply(lambda x: auto.validar_whatsapp_api(x) if pd.notnull(x) and str(x).strip() != "" else False)]
                    total_wa_invalid = initial_len - len(df_consolidated)
                else:
                    st.warning("⚠️ Coluna de telefone não encontrada para pré-validação.")

        # Persistir no session_state
        st.session_state["_consol_applied"] = True
        st.session_state["_consol_df"] = df_consolidated.copy()
        st.session_state["_consol_log"] = log_messages
        st.session_state["_consol_dropped"] = pre_guillotine - post_guillotine
        st.session_state["_consol_promoted"] = total_promoted
        st.session_state["_consol_discarded"] = total_discarded_cells
        st.session_state["_consol_wa_invalid"] = total_wa_invalid
        st.rerun()

# ── 6e. Recuperar estado após rerun ──
if st.session_state.get("_consol_applied"):
    df_consolidated = st.session_state["_consol_df"].copy()
    for msg in st.session_state.get("_consol_log", []):
        st.success(msg)

    # Métricas de feedback
    promoted = st.session_state.get("_consol_promoted", 0)
    discarded = st.session_state.get("_consol_discarded", 0)
    dropped = st.session_state.get("_consol_dropped", 0)

    if promoted > 0 or discarded > 0:
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("🏆 Contatos Promovidos", f"{promoted:,}", help="Valores aceites por terem status positivo.")
        mc2.metric("🚫 Células Rejeitadas", f"{discarded:,}", help="Valores ignorados por status inválido.")
        mc3.metric("🔪 Linhas Guilhotinadas", f"{dropped:,}", help="Linhas removidas por ficarem sem contato.")
    elif dropped > 0:
        st.info(f"🔪 Guilhotina removeu **{dropped:,}** linhas sem contato.")
    
    if st.session_state.get("_consol_wa_invalid", 0) > 0:
        st.warning(f"🛡️ Evolution API descartou **{st.session_state['_consol_wa_invalid']:,}** leads sem conta no WhatsApp.")

    st.markdown("**Pré-visualização após consolidação:**")
    st.dataframe(df_consolidated.head(8), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. PAINEL DE EXPORTAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("7 · Exportação Final")

df_final = df_consolidated.copy()

# ── Métricas ──
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("Leads Iniciais", f"{st.session_state.initial_count:,}")
col_m2.metric("Leads Purificados", f"{len(df_final):,}")
col_m3.metric(
    "Taxa de Retenção",
    f"{(len(df_final) / st.session_state.initial_count * 100):.1f}%"
    if st.session_state.initial_count > 0
    else "—",
)

st.markdown("**Pré-visualização (10 primeiros registos limpos):**")
st.dataframe(df_final.head(10), use_container_width=True)

# ── Exportação CSV (utf-8-sig para compatibilidade Excel/Windows) ──
csv_output = df_final.to_csv(index=False, encoding="utf-8-sig")

st.download_button(
    label="⬇️ Descarregar CSV Purificado",
    data=csv_output,
    file_name="leads_purificados.csv",
    mime="text/csv",
    help="Ficheiro codificado em UTF-8 com BOM — abre corretamente no Excel (Windows).",
    type="primary",
    use_container_width=True,
)

def executar_guilhotina(df):
    """Critério de Exclusão: Remove linhas sem e-mail ou telefone.
    Limpa caracteres especiais do telefone antes de verificar se está vazio.
    """
    before = len(df)
    # Procura colunas de email e telefone
    col_email = next((c for c in df.columns if "email" in c.lower()), None)
    col_tel = next((c for c in df.columns if "tele" in c.lower() or "phone" in c.lower() or "whats" in c.lower()), None)
    
    if not col_email and not col_tel:
        return df, 0
        
    def has_contact(row):
        email = str(row.get(col_email, "")).strip() if col_email else ""
        tel = str(row.get(col_tel, "")).strip() if col_tel else ""
        
        # Limpeza robusta do telefone para validar se há conteúdo real
        tel_limpo = re.sub(r'\D', '', tel)
        
        return (email != "" and email.lower() != "nan") or (tel_limpo != "")

    df_clean = df[df.apply(has_contact, axis=1)].copy()
    return df_clean, before - len(df_clean)

st.caption("NXT Purifier · Processamento local · Dados nunca saem da máquina.")
