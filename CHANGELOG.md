# 📜 NXT OS — Changelog Evolutivo

Acompanhamento de progresso e marcos do sistema de inteligência CRM.

---

## [1.4.0-beta] — 2026-04-25
### ✨ "Direct-to-CRM & Robustness Update"
- **Integração Direta**: Implementada a função `enviar_notion_direto` que confia 100% no DataFrame purificado.
- **Segurança JSON**: Adicionada sanitização global para valores `NaN` do Pandas, eliminando erros de `InvalidJSONError`.
- **Limpeza de Selects**: Remoção automática de vírgulas e caracteres especiais em campos de seleção do Notion.
- **Fallback de Cascata**: Inteligência Outscraper agora possui fallback para colunas mapeadas manualmente.
- **Correção de UI**: Corrigido bug nos scripts de LinkedIn/Instagram que causava erro de atributo.

## [1.3.0] — 2026-04-24
### 🛡️ "Purification & Filtering"
- **Módulo Purifier**: Implementação da "Guilhotina" (descarte de leads sem contato) e "Smart Erase" (deduplicação agressiva).
- **Mapeamento Heurístico v3**: Análise híbrida (Header + Amostra de 30 linhas) para detecção automática de colunas.
- **Persistência de Estado**: Resolvido problema de reset do CSV ao navegar entre módulos do Streamlit.

## [1.2.0] — 2026-04-23
### 🧠 "Intelligence Engine"
- **Cascata Outscraper**: Implementação da validação de e-mails em cascata (Status: DELIVERABLE).
- **Extração de Decisores**: Mapeamento inteligente de nomes baseados em e-mails validados.
- **Mapeamento Heurístico v1/v2**: Primeira versão da detecção automática de redes sociais e sites.

## [1.1.0] — 2026-04-15
### 🎯 "Active Prospecting"
- **Módulo de Disparos**: Adicionados botões de WhatsApp, E-mail, LinkedIn e Instagram.
- **Scripts Personalizados**: Sistema de templates dinâmicos com variáveis `[Empresa]` e `[Diagnóstico]`.
- **Integração Gemini**: Geração de diagnósticos técnicos automáticos para abordagem.

## [1.0.0] — 2026-03-27
### 🚀 "Foundation"
- **MVP**: Estrutura base do CRM no Streamlit conectada à API do Notion.
- **CRUD Básico**: Sincronização de leads e atualização de status.
