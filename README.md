Necessário python >=3.8
S.O >= 10


1. pip install -r requirements.txt
2. change OPENAI_API_KEY IN .env
3. execute com privilegios o cmd, depois rode o main.py
3.1. alternadamente, pode-se criar um executável para abrir diretamente como admin:
        pip install pyinstaller
        pyinstaller --onefile --windowed main.py
