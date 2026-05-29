POPPE ERP PRO V19 CLOUD PRO

Incluído:
- Login multiusuário real
- Permissões por perfil
- Painel administrativo
- CRM visual
- Contrato PDF automático
- PIX preparado
- WhatsApp por link e campos para API
- PWA instalável no celular
- Fotos e assinatura digital
- Financeiro/contas a receber
- Backup completo
- Atualizador preparado
- Domínio próprio documentado

Usuário inicial:
admin
Senha:
admin123

Railway:
Build Command: pip install -r requirements.txt
Start Command: python app.py

Variables:
DATABASE_URL = URL do PostgreSQL
SECRET_KEY = chave forte

Domínio:
Railway > Settings > Networking > Custom Domain
Adicionar: erp.poppeservicos.com.br
No provedor do domínio: CNAME erp -> endereço indicado pelo Railway

Observação:
WhatsApp automático real depende de API oficial/serviço externo.
PIX real depende de gateway/banco com API.
App Android/iPhone nativo exige Flutter/React Native; esta versão é PWA instalável.
