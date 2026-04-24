import os
import time
import pandas as pd
import requests
import logging
import urllib.parse
from datetime import datetime, timedelta
from urllib.parse import quote
from dotenv import load_dotenv

# Import robusto do Gemini — evita conflito de namespace do Google
try:
    from google import genai
except ImportError as e:
    raise ImportError(
        "Biblioteca 'google-genai' não encontrada. Execute: pip install google-genai==1.0.0"
    ) from e

# --- 1. CONFIGURAÇÃO DE AMBIENTE ---
# Busca .env de forma absoluta — funciona local, Codespaces e Streamlit Cloud
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_BASE_DIR, '.env'))
if not os.getenv("NOTION_TOKEN"):
    load_dotenv(dotenv_path=os.path.join(_BASE_DIR, '..', 'automation', '.env'))

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID  = os.getenv("DATABASE_ID")
GEMINI_KEY   = os.getenv("GEMINI_KEY")

# Fallback para Streamlit Cloud (st.secrets) se variável de ambiente não existir
try:
    import streamlit as _st
    if not NOTION_TOKEN:
        NOTION_TOKEN = _st.secrets.get("NOTION_TOKEN", "")
    if not DATABASE_ID:
        DATABASE_ID  = _st.secrets.get("DATABASE_ID",  "")
    if not GEMINI_KEY:
        GEMINI_KEY   = _st.secrets.get("GEMINI_KEY",  "")
except Exception:
    pass  # Streamlit não disponível (ex: script CLI)

# ── Cache de dados para Dashboard/Métricas ──────────────────────────────────
try:
    from streamlit import cache_data as _cache_data

    @_cache_data(ttl=3600)
    def buscar_dados_completos():
        """Busca TODOS os registros do Notion com paginação.
        Cache de 1 hora via @st.cache_data — evita chamadas repetidas à API.
        Retorna lista de dicts com campos essenciais para o Dashboard.
        """
        url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        all_results, cursor = [], None

        def _get_val(p, name):
            prop = p.get(name, {})
            ptype = prop.get("type")
            if ptype == "select":
                return (prop.get("select") or {}).get("name", "")
            elif ptype == "status":
                return (prop.get("status") or {}).get("name", "")
            elif ptype == "multi_select":
                items = prop.get("multi_select") or []
                return ", ".join([i.get("name", "") for i in items])
            elif ptype == "rich_text":
                rt = prop.get("rich_text", [])
                return rt[0]["text"]["content"] if rt else ""
            elif ptype == "formula":
                f = prop.get("formula", {})
                ftype = f.get("type")
                return str(f.get(ftype, "")) if ftype else ""
            return ""

        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor

            res = requests.post(url, headers=headers, json=body)
            if res.status_code != 200:
                break

            data = res.json()
            for r in data.get("results", []):
                props = r.get("properties", {})

                titulo = props.get("Empresa", {}).get("title", [])
                empresa = titulo[0]["text"]["content"] if titulo else "Sem Nome"

                status_obj = props.get("Status de Contato", {}).get("status", {})
                status = status_obj.get("name", "") if status_obj else ""

                # Lógica de Decisor baseada no nome (conforme solicitado pelo usuário)
                nome_decisor = _get_val(props, "Nome do Decisor")
                decisor = "Sim" if nome_decisor.strip() else "Não"

                meio    = _get_val(props, "Meio de Contato")
                motivo  = _get_val(props, "Motivo")
                
                # Valor Potencial (Number)
                valor_raw = props.get("Valor Potencial", {}).get("number")
                try:
                    valor = float(valor_raw) if valor_raw is not None else 0.0
                except:
                    valor = 0.0

                tipo_obj = props.get("Tipo de Negócio", {}).get("select", {})
                tipo = tipo_obj.get("name", "Outros") if tipo_obj else "Outros"

                avaliacao = props.get("Avaliação", {}).get("number") or 0.0

                all_results.append({
                    "Empresa":           empresa,
                    "Status de Contato": status,
                    "Tipo de Negócio":   tipo,
                    "Avaliação":         float(avaliacao),
                    "Decisor":           decisor,
                    "Meio de Contato":   meio,
                    "Motivo":            motivo,
                    "Valor Potencial":   valor
                })

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        return all_results

except Exception:
    # Fallback para execução CLI sem Streamlit instalado
    def buscar_dados_completos():
        return []


# Inicialização segura do Gemini
if GEMINI_KEY:
    client = genai.Client(api_key=GEMINI_KEY)
else:
    client = None  # Gemini desativado — diagnóstico não disponível

MODEL_NAME = "gemini-2.0-flash"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- CONFIGURAÇÃO DE LOGS (Independente) ---
path_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'automacao.log')
logger = logging.getLogger("automacao_nxt")
logger.setLevel(logging.INFO)

# Evita duplicar handlers se o script for importado várias vezes
if not logger.handlers:
    fh = logging.FileHandler(path_log, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

def log(msg, level="info"):
    print(msg)
    if level == "error": logger.error(msg)
    else: logger.info(msg)

# Log inicial para confirmar que o script carregou
log("🚀 Script automacao_nxt.py carregado com sucesso.")

# --- 2. MAPEAMENTO E PADRONIZAÇÃO ---
MAPA_COLUNAS = {
    'empresa': ['website_title', 'linkedin.li_companies.name', 'Empresa', 'name', 'company_name', 'Nome', 'title'],
    'site': ['Site Atual', 'site', 'website', 'URL'],
    'telefone': ['Telefone', 'phone', 'phone_number', 'numero'],
    'email': ['email', 'E-mail', 'Email'],
    'tipo_negocio': ['Tipo de Negócio', 'category', 'categoria'],
    'localizacao': ['Localização', 'city', 'address', 'Address'],
    'decisor': ['Nome do Decisor', 'Owner', 'Decision Maker'],
    'avaliacao': ['Avaliação', 'Rating'],
    'qtd_avaliacoes': ['Quantidade de Avaliações', 'reviews', 'reviews_count'],
    'status': ['Status de Contato', 'Status', 'status_de_contato', 'Situação'],
    'disparo': ['Disparo', 'disparo', 'status_disparo'],
    'motivo': ['Motivo', 'motivo', 'reason'],
    'meio_contato': ['Meio de Contato', 'meio', 'contact_method'],
    'observacoes': ['Observações', 'Observação', 'notes'],
    'primeiro_contato': ['Primeiro Contato', 'Data de Primeiro Contato', 'primeiro_contato'],
    'data_resposta': ['Data de Resposta', 'Data da Resposta', 'data_resposta']
}

def categorizar_negocio(raw_tipo):
    if not raw_tipo: return "Outros"
    t = raw_tipo.lower()
    if any(x in t for x in ["marketing", "publicidade", "tráfego", "ads", "comunicação"]):
        return "Agência de Marketing"
    if any(x in t for x in ["consultoria", "assessoria"]):
        return "Consultoria"
    if any(x in t for x in ["software", "tecnologia", "ti", "sistemas"]):
        return "Tecnologia/SaaS"
    return raw_tipo.strip().title()[:100]

def buscar_dado(row, categoria):
    colunas_csv = {str(col).strip().lower(): col for col in row.index}
    for sinonimo in MAPA_COLUNAS[categoria]:
        sn = str(sinonimo).strip().lower()
        if sn in colunas_csv:
            v = row[colunas_csv[sn]]
            # Se for Outscraper, pode haver campos vazios como "nan" ou "None"
            if pd.notnull(v) and str(v).strip().lower() not in ["", "nan", "none"]:
                return str(v).strip()
    return None

def consolidar_contatos_outscraper(row):
    """Lógica de Cascata para Leads do Outscraper:
    1. E-mail: Valida status (DELIVERABLE/CATCH-ALL) em cascata (1->3).
    2. Decisor: Extrai nome do dono do e-mail validado.
    3. Telefone: Cascata de phone_1 até phone_3.
    4. Redes: LinkedIn, Instagram, Facebook.
    """
    res = {}
    
    # --- 1. CASCATA DE E-MAILS ---
    email_valido = None
    decisor_valido = None
    
    for i in range(1, 4):
        e_col = f"email_{i}"
        s_col = f"email_{i}.emails_validator.status"
        n_col = f"email_{i}_full_name"
        
        email = str(row.get(e_col, "")).strip()
        status = str(row.get(s_col, "")).strip().upper()
        nome = str(row.get(n_col, "")).strip()
        
        if email and email.lower() != "nan" and status in ["DELIVERABLE", "CATCH-ALL"]:
            email_valido = email
            decisor_valido = nome if nome and nome.lower() != "nan" else None
            break
            
    res["email"] = email_valido
    res["decisor"] = decisor_valido
    
    # --- 2. CASCATA DE TELEFONES ---
    tel_valido = None
    for i in range(1, 4):
        t_col = f"phone_{i}"
        tel = str(row.get(t_col, "")).strip()
        if tel and tel.lower() != "nan":
            # Limpa e formata (+55...)
            tel_limpo = "".join(filter(str.isdigit, tel))
            if tel_limpo:
                if not tel_limpo.startswith("55") and len(tel_limpo) >= 10:
                    tel_valido = f"+55{tel_limpo}"
                else:
                    tel_valido = f"+{tel_limpo}"
                break
    res["telefone"] = tel_valido
    
    # --- 3. REDES SOCIAIS ---
    res["linkedin"] = str(row.get("linkedin", "")).strip() if pd.notnull(row.get("linkedin")) else ""
    res["instagram"] = str(row.get("instagram", "")).strip() if pd.notnull(row.get("instagram")) else ""
    res["facebook"] = str(row.get("facebook", "")).strip() if pd.notnull(row.get("facebook")) else ""
    
    for rede in ["linkedin", "instagram", "facebook"]:
        if res[rede].lower() == "nan": res[rede] = ""

    # Determinar Meio de Contato Inicial
    if email_valido:
        res["meio_contato"] = "E-mail"
    elif tel_valido:
        res["meio_contato"] = "WhatsApp"
    else:
        res["meio_contato"] = ""
        
    return res

# --- 3. INTELIGÊNCIA E VALIDAÇÃO ---

def verificar_duplicado(empresa, site, localizacao):
    """
    Verifica se a empresa já existe no Notion.
    """
    if not empresa:
        return None

    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"

    query = {
        "filter": {
            "property": "Empresa",
            "title": { "equals": empresa.strip() }
        },
        "page_size": 5
    }
    
    try:
        res = requests.post(url, headers=HEADERS, json=query)
        if res.status_code != 200:
            log(f"⚠️ Erro ao verificar duplicado para '{empresa}': {res.status_code}", "error")
            return None

        results = res.json().get("results", [])

        if not results:
            return None  # Nenhum encontrado → é novo

        if len(results) == 1:
            page_id = results[0]["id"]
            log(f"♻️  Duplicado encontrado: '{empresa}' → page_id {page_id}")
            return page_id

        if site and str(site).lower() != 'none':
            for r in results:
                site_notion = r.get("properties", {}).get("Site Atual", {}).get("url", "")
                if site_notion and site_notion.strip().rstrip("/") == site.strip().rstrip("/"):
                    page_id = r["id"]
                    log(f"♻️  Duplicado encontrado (via site): '{empresa}' → page_id {page_id}")
                    return page_id

        page_id = results[0]["id"]
        log(f"♻️  Duplicado encontrado (1º resultado): '{empresa}' → page_id {page_id}")
        return page_id

    except Exception as e:
        log(f"⚠️ Exceção ao verificar duplicado para '{empresa}': {e}", "error")
        return None

def gerar_rid(site, empresa):

    if not site or "http" not in str(site):
        return "Site inválido ou ausente."
    
    # Gemini não configurado
    if not client:
        return "Diagnóstico indisponível (GEMINI_KEY não configurada)."
    
    # Detecção de Redes Sociais
    site_lower = str(site).lower()
    is_social = any(x in site_lower for x in ["instagram.com", "linkedin.com", "facebook.com"])
    
    if is_social:
        prompt = f"Analise o perfil de rede social desta empresa ({site}) e identifique 2 oportunidades de automação de atendimento ou captura de leads. Seja direto e use tom profissional."
    else:
        prompt = f"Analise o site {site} da empresa {empresa}. Liste 3 falhas técnicas B2B. Curto."
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={'http_options': {'timeout': 10}} # Timeout de 10s para não travar
        )
        return response.text.strip()
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            return "Diagnóstico pendente (Cota excedida)"
        
        print(f"⚠️ Erro Gemini em {empresa}: {e}")
        return "Erro no diagnóstico."

# --- 4. COMUNICAÇÃO COM NOTION ---

import urllib.parse

def obter_script_base(canal):
    """Retorna o script padrão para cada canal de prospecção."""
    scripts = {
        "whatsapp": "Olá, sou o Nathan da NXT. Analisei o site da [Empresa] e notei: [Diagnóstico]. Podemos conversar?",
        "email": "Olá,\n\nAnalisei o site da [Empresa] e identifiquei oportunidades interessantes de otimização baseadas em: [Diagnóstico].\n\nPodemos agendar uma breve conversa?\n\nAtenciosamente,\nNathan - NXT",
        "linkedin": "Olá! Vi o trabalho da [Empresa] e achei muito interessante. Notei alguns pontos sobre [Diagnóstico] que gostaria de compartilhar. Vamos conectar?",
        "instagram": "Olá pessoal da [Empresa]! Adorei o perfil de vocês. Notei algo no site que pode interessar: [Diagnóstico]. Sucesso!"
    }
    return scripts.get(canal, "")

def criar_link_whatsapp(telefone, empresa, diagnostico, script_base=None):
    if not telefone or str(telefone).lower() == 'none':
        return None
    
    tel_limpo = "".join(filter(str.isdigit, str(telefone)))
    diag_limpo = str(diagnostico).replace('\n', ' ')[:200] if diagnostico else "análise técnica"
    
    base = script_base if script_base else obter_script_base("whatsapp")
    msg = base.replace("[Empresa]", empresa).replace("[Diagnóstico]", diag_limpo)
    
    msg_codificada = urllib.parse.quote(msg)
    return f"https://wa.me/{tel_limpo}?text={msg_codificada}"

def gerar_link_email(email, empresa, diagnostico, script_base=None):
    if not email or str(email).lower() == 'none':
        return None
    
    assunto = urllib.parse.quote(f"Parceria NXT x {empresa}")
    diag_limpo = str(diagnostico).replace('\n', ' ')[:200] if diagnostico else "análise técnica"
    
    base = script_base if script_base else obter_script_base("email")
    corpo = base.replace("[Empresa]", empresa).replace("[Diagnóstico]", diag_limpo)
    corpo_codificado = urllib.parse.quote(corpo)
    
    return f"mailto:{email}?subject={assunto}&body={corpo_codificado}"

def gerar_link_linkedin(perfil_url):
    if not perfil_url or str(perfil_url).lower() == 'none' or "linkedin.com" not in str(perfil_url):
        return None
    return str(perfil_url).strip()

def gerar_link_instagram(perfil_url):
    if not perfil_url or str(perfil_url).lower() == 'none' or "instagram.com" not in str(perfil_url):
        return None
    return str(perfil_url).strip()

def enviar_notion(dados, page_id=None):
    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        http_method = requests.patch
    else:
        url = "https://api.notion.com/v1/pages"
        http_method = requests.post

    def limpar(v):
        return str(v).strip() if v and str(v).lower() != 'none' else ""

    # Status
    status_csv = dados.get('status')
    if str(status_csv).strip() == 'Arquivar':
        status_final = 'Follow up'  # Nome exato no Notion (sem hífen)
    else:
        status_final = str(status_csv).strip() if status_csv and str(status_csv).lower() != 'none' else "Não contactado"

    # Disparo
    disparo_csv = dados.get('disparo')
    disparo_final = str(disparo_csv).strip() if disparo_csv and str(disparo_csv).lower() != 'none' else "Aguardando disparo"
    
    # Motivo
    motivo_csv = dados.get('motivo')
    motivo_final = str(motivo_csv).strip() if motivo_csv and str(motivo_csv).lower() != 'none' else "Neutro"

    # Meio de Contato
    meio_csv = dados.get('meio_contato')
    meio_final = str(meio_csv).strip() if meio_csv and str(meio_csv).lower() != 'none' else ""
    
    def formatar_data(data_raw):
        if not data_raw or str(data_raw).lower() == 'none': return None
        try:
            return pd.to_datetime(data_raw).strftime('%Y-%m-%d')
        except:
            return None

    p_contato = formatar_data(dados.get('primeiro_contato'))
    d_resposta = formatar_data(dados.get('data_resposta'))

    try:
        val_avaliacao = float(str(dados.get('avaliacao', '0')).replace(',', '.'))
    except:
        val_avaliacao = 0.0

    try:
        val_qtd = int(float(str(dados.get('qtd_avaliacoes', '0')).replace('None', '0')))
    except:
        val_qtd = 0

    link_wa = criar_link_whatsapp(dados.get('telefone'), dados.get('empresa'), dados.get('rid'))

    propriedades = {
        "Empresa": { "title": [{ "text": { "content": limpar(dados.get('empresa')) or "Sem Nome" } }] },
        "Status de Contato": { "status": { "name": status_final } },
        "Avaliação": { "number": val_avaliacao },
        "Quantidade de Avaliações": { "number": val_qtd },
        "Site Atual": { "url": dados.get('site') if dados.get('site') else None },
        "Telefone": { "phone_number": dados.get('telefone') if dados.get('telefone') else None },
        "E-mail": { "email": dados.get('email') if dados.get('email') else None },
        "LinkedIn": { "url": dados.get('linkedin') if dados.get('linkedin') else None },
        "Instagram": { "url": dados.get('instagram') if dados.get('instagram') else None },
        "Facebook": { "url": dados.get('facebook') if dados.get('facebook') else None },
        "Link WhatsApp": { "url": link_wa },
        "Disparo": { "select": { "name": disparo_final } }
    }

    if p_contato:
        propriedades["Primeiro Contato"] = { "date": { "start": p_contato } }
    if d_resposta:
        propriedades["Data da Resposta"] = { "date": { "start": d_resposta } }

    if meio_final:
        propriedades["Meio de Contato"] = { "select": { "name": meio_final } }

    if dados.get('tipo_negocio') and dados.get('tipo_negocio') != "Outros":
        propriedades["Tipo de Negócio"] = { "select": { "name": dados['tipo_negocio'] } }
    
    campos_texto = {
        "Localização": dados.get('localizacao'),
        "Nome do Decisor": dados.get('decisor'),
        "Diagnóstico Gemini": dados.get('rid'),
        "Observações": dados.get('observacoes')
    }
    for nome, valor in campos_texto.items():
        v_limpo = limpar(valor)
        # Limite de 2000 chars da API do Notion para rich_text
        v_limpo = v_limpo[:2000] if v_limpo else ""
        if v_limpo or nome not in ["Observações", "Nome do Decisor"]:
            propriedades[nome] = { "rich_text": [{ "text": { "content": v_limpo } }] if v_limpo else [] }

    # Motivo: só envia se tiver valor definido (evita erro 400 se opção não existir)
    if motivo_final and motivo_final != "Neutro":
        propriedades["Motivo"] = { "select": { "name": motivo_final } }
    else:
        # Remove do payload se "Neutro" (pode não existir no Notion)
        propriedades.pop("Motivo", None)

    payload = {"properties": propriedades}
    
    if not page_id:
        payload["parent"] = {"database_id": DATABASE_ID}

    res = http_method(url, headers=HEADERS, json=payload)
    
    if res.status_code not in [200, 201, 202]:
        try:
            resp_body = res.json()
            err_msg = f"❌ Erro Notion em {dados.get('empresa')}: HTTP {res.status_code}"
            err_detail = f"   ↳ Mensagem: {resp_body.get('message', 'N/A')}"
            err_path = f"   ↳ Path: {resp_body.get('path', 'N/A')}"
            err_code = f"   ↳ Code: {resp_body.get('code', 'N/A')}"
        except Exception:
            err_msg = f"❌ Erro Notion em {dados.get('empresa')}: HTTP {res.status_code}"
            err_detail, err_path, err_code = "", "", ""
        log(err_msg, "error")
        log(err_detail, "error")
        log(err_path, "error")
        log(err_code, "error")
        return False
    else:
        log(f"✅ {dados.get('empresa')} {'atualizada' if page_id else 'criada'} com sucesso.")
        return True

def buscar_leads_notion():
    """Busca leads para prospecção: Status='Não contactado' e Disparo='Aguardando disparo'"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    
    query = {
        "filter": {
            "and": [
                {
                    "property": "Status de Contato",
                    "status": { "equals": "Não contactado" }
                },
                {
                    "property": "Disparo",
                    "select": { "equals": "Aguardando disparo" }
                }
            ]
        }
    }
    
    try:
        res = requests.post(url, headers=HEADERS, json=query)
        if res.status_code == 200:
            results = res.json().get("results", [])
            leads = []
            for r in results:
                props = r.get("properties", {})
                
                def get_text(prop_name):
                    rt = props.get(prop_name, {}).get("rich_text", [])
                    return rt[0]["text"]["content"] if rt else ""

                def get_title():
                    t = props.get("Empresa", {}).get("title", [])
                    return t[0]["text"]["content"] if t else "Sem Nome"

                leads.append({
                    "id": r["id"],
                    "empresa": get_title(),
                    "site": props.get("Site Atual", {}).get("url", ""),
                    "telefone": props.get("Telefone", {}).get("phone_number", ""),
                    "email": props.get("E-mail", {}).get("email", ""),
                    "linkedin": props.get("LinkedIn", {}).get("url", ""),
                    "instagram": props.get("Instagram", {}).get("url", ""),
                    "diagnostico": get_text("Diagnóstico Gemini"),
                    "link_wa": props.get("Link WhatsApp", {}).get("url", "")
                })
            return leads
        else:
            log(f"❌ Erro ao buscar leads: {res.status_code}", "error")
            return []
    except Exception as e:
        log(f"❌ Exceção ao buscar leads: {e}", "error")
        return []

def atualizar_status_disparo(page_id):
    """Atualiza o lead após o disparo:
    - Disparo            → 'Realizado'
    - Status de Contato  → 'Tentativa de contato'
    - Primeiro Contato   → data de HOJE (ISO 8601)
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    hoje = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "properties": {
            "Disparo":           { "select": { "name": "Realizado" } },
            "Status de Contato": { "status": { "name": "Tentativa de contato" } },
            "Primeiro Contato":  { "date":   { "start": hoje } }
        }
    }

    try:
        res = requests.patch(url, headers=HEADERS, json=payload)
        if res.status_code not in [200, 202]:
            try:
                body = res.json()
                log(f"❌ atualizar_status_disparo: HTTP {res.status_code} | {body.get('message')} | path: {body.get('path')}", "error")
            except Exception:
                log(f"❌ atualizar_status_disparo: HTTP {res.status_code}", "error")
            return False
        return True
    except Exception as e:
        log(f"❌ Erro ao atualizar status: {e}", "error")
        return False


def calcular_proximo_dia_util(data_base: datetime, dias: int) -> datetime:
    """Soma `dias` corridos a data_base e, se cair em fim de semana, avança para segunda."""
    resultado = data_base + timedelta(days=dias)
    # 5 = sábado, 6 = domingo
    if resultado.weekday() == 5:   # sábado → segunda
        resultado += timedelta(days=2)
    elif resultado.weekday() == 6: # domingo → segunda
        resultado += timedelta(days=1)
    return resultado


def buscar_leads_follow_up():
    """Busca leads onde Status = 'Tentativa de contato' OU 'Follow up'.
    Retorna lista com campos para a esteira de acompanhamento.
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"

    query = {
        "filter": {
            "or": [
                { "property": "Status de Contato", "status": { "equals": "Tentativa de contato" } },
                { "property": "Status de Contato", "status": { "equals": "Follow up" } }
            ]
        }
    }

    # Helpers definidos FORA do loop — evita closure bug do Python
    def _get_text(props, prop_name):
        rt = props.get(prop_name, {}).get("rich_text", [])
        return rt[0]["text"]["content"] if rt else ""

    def _get_title(props):
        t = props.get("Empresa", {}).get("title", [])
        return t[0]["text"]["content"] if t else "Sem Nome"

    def _get_status(props):
        return props.get("Status de Contato", {}).get("status", {}).get("name", "")

    def _get_date(props, field):
        d = props.get(field, {}).get("date")
        return d["start"] if d else None

    try:
        res = requests.post(url, headers=HEADERS, json=query)
        if res.status_code != 200:
            log(f"❌ buscar_leads_follow_up: HTTP {res.status_code} — {res.text[:200]}", "error")
            return []

        leads = []
        for r in res.json().get("results", []):
            props = r.get("properties", {})
            leads.append({
                "id":              r["id"],
                "empresa":         _get_title(props),
                "site":            props.get("Site Atual", {}).get("url", ""),
                "telefone":        props.get("Telefone", {}).get("phone_number", ""),
                "email":           props.get("E-mail", {}).get("email", ""),
                "linkedin":        props.get("LinkedIn", {}).get("url", ""),
                "instagram":       props.get("Instagram", {}).get("url", ""),
                "diagnostico":     _get_text(props, "Diagnóstico Gemini"),
                "link_wa":         props.get("Link WhatsApp", {}).get("url", ""),
                "status":          _get_status(props),
                "primeiro_contato":_get_date(props, "Primeiro Contato"),
            })
        log(f"✅ buscar_leads_follow_up: {len(leads)} leads encontrados.")
        return leads

    except Exception as e:
        log(f"❌ Exceção em buscar_leads_follow_up: {e}", "error")
        return []


def atualizar_status_manual(page_id: str, novo_status: str) -> bool:
    """Muda 'Status de Contato' para qualquer valor válido no Notion.
    Usado para transições rápidas na esteira de Follow-up.
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "Status de Contato": { "status": { "name": novo_status } }
        }
    }
    try:
        res = requests.patch(url, headers=HEADERS, json=payload)
        if res.status_code not in [200, 202]:
            try:
                body = res.json()
                log(f"❌ atualizar_status_manual ({novo_status}): HTTP {res.status_code} | {body.get('message')}", "error")
            except Exception:
                pass
            return False
        return True
    except Exception as e:
        log(f"❌ Erro em atualizar_status_manual: {e}", "error")
        return False

# --- 5. LOOP PRINCIPAL ---

def processar_leads(arquivo_csv):
    if not os.path.exists(arquivo_csv):
        print("❌ Arquivo leads.csv não encontrado.")
        return

    try:
        df = pd.read_csv(arquivo_csv)
    except Exception as e:
        print(f"❌ Erro ao ler o arquivo CSV: {e}")
        return
    print(f"🚀 Iniciando processamento de {len(df)} leads...")
    erros = 0
    processados = 0

    for _, row in df.iterrows():
        empresa = buscar_dado(row, 'empresa')
        site = buscar_dado(row, 'site')
        localizacao = buscar_dado(row, 'localizacao')
        
        if not empresa: continue

        try:
            page_id = verificar_duplicado(empresa, site, localizacao)
            
            if page_id:
                msg_status = "Atualizando"
            else:
                msg_status = "Criando"

            log(f"🔍 {msg_status}: {empresa}")
            
            status_ok = enviar_notion({
                'empresa': empresa,
                'site': site,
                'telefone': buscar_dado(row, 'telefone'),
                'email': buscar_dado(row, 'email'),
                'status': buscar_dado(row, 'status'),
                'tipo_negocio': categorizar_negocio(buscar_dado(row, 'tipo_negocio')),
                'localizacao': localizacao,
                'decisor': buscar_dado(row, 'decisor'),
                'avaliacao': buscar_dado(row, 'avaliacao'),
                'qtd_avaliacoes': buscar_dado(row, 'qtd_avaliacoes'),
                'rid': gerar_rid(site, empresa),
                'disparo': buscar_dado(row, 'disparo'),
                'motivo': buscar_dado(row, 'motivo'),
                'meio_contato': buscar_dado(row, 'meio_contato'),
                'observacoes': buscar_dado(row, 'observacoes'),
                'primeiro_contato': buscar_dado(row, 'primeiro_contato'),
                'data_resposta': buscar_dado(row, 'data_resposta')
            }, page_id=page_id)
            
            if not status_ok:
                erros += 1
            else:
                processados += 1
            
            time.sleep(0.5) 
        except Exception as e:
            log(f"❌ Falha crítica no lead {empresa}: {e}", "error")
            erros += 1

    if erros > 0 and processados == 0:
        log(f"⚠️ Processamento falhou totalmente ({erros} erros).", "error")
        return False 
    
    log(f"🏁 Concluído: {processados} sucessos, {erros} falhas.")
    return True 

if __name__ == "__main__":
    processar_leads("leads.csv")