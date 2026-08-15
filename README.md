# Multiplayer Snake

Лаунчер мультиплеера для **Minecraft PE 1.1.5**.

## Что уже есть

- Регистрация / вход (JWT)
- Создание и список активных миров
- Консольный клиент (Termux + ПК)
- База данных на Neon (PostgreSQL)

## Структура

```
multiplayer-snake/
├── backend/          # FastAPI сервер
│   ├── main.py
│   ├── models.py
│   ├── auth.py
│   └── ...
└── client/           # Консольный клиент
    ├── client.py
    └── config.py
```

## Запуск бэкенда (локально)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Документация API: http://127.0.0.1:8000/docs

## Запуск клиента

```bash
cd client
pip install -r requirements.txt
python client.py
```

## Дальше

- [ ] Фейковый LAN для появления мира в Друзьях Minecraft 1.1.5
- [ ] Проксирование трафика
- [ ] Деплой бэкенда на Render.com
- [ ] Улучшенный интерфейс
