POPPE ERP PRO V18.1 CLOUD - Supabase/PostgreSQL + Render/Railway

O que foi ajustado:
- Suporte a DATABASE_URL.
- Local continua usando SQLite.
- Online usa PostgreSQL/Supabase.
- Arquivos prontos para deploy:
  render.yaml
  Procfile
  runtime.txt
  .env.example

COMO RODAR LOCAL:
py -3.14 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py

COMO TESTAR CLOUD LOCAL:
1. Copie .env.example para .env
2. Cole sua DATABASE_URL do Supabase.
3. Rode app.py.
4. Acesse:
   http://127.0.0.1:8080/cloud
   http://127.0.0.1:8080/health

SUPABASE:
1. Crie um projeto.
2. Vá em Project Settings > Database.
3. Copie a connection string URI.
4. Troque [YOUR-PASSWORD] pela senha do banco.
5. Use como DATABASE_URL.

RENDER:
1. Suba este projeto no GitHub.
2. No Render, crie Web Service.
3. Build Command:
   pip install -r requirements.txt
4. Start Command:
   gunicorn app:app
5. Environment:
   DATABASE_URL = sua connection string do Supabase
   SECRET_KEY = qualquer chave forte

RAILWAY:
1. Suba no GitHub.
2. Crie projeto no Railway.
3. Deploy from GitHub.
4. Configure DATABASE_URL.
5. Start Command:
   gunicorn app:app

Usuário inicial preparado no banco:
admin
Senha:
admin123

IMPORTANTE:
Em hospedagem gratuita, arquivos enviados como fotos/PDF podem ser temporários.
O próximo passo profissional é salvar imagens/PDFs no Supabase Storage.
