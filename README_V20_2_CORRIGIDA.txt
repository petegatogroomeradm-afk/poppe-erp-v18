POPPE ERP PRO V20.2 CORRIGIDA

Correções:
- Corrige erro 500 em /agenda.
- Corrige erro 500 em /financeiro.
- Cria automaticamente as tabelas agenda_mobile e recebimentos_mobile no PostgreSQL existente.
- Adiciona rota administrativa /admin/corrigir-banco para forçar correção do banco caso necessário.
- Mantém V20 Enterprise + edição de usuários da V20.1.

Após subir no Render:
1. Acesse /admin/corrigir-banco uma vez logado como admin.
2. Teste /agenda.
3. Teste /financeiro.

Deploy:
git init
git add .
git commit -m "V20.2 corrige agenda financeiro postgres"
git branch -M main
git remote remove origin
git remote add origin https://github.com/petegatogroomeradm-afk/poppe-erp-v18.git
git push -u origin main --force
