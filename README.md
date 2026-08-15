# Multiplayer Snake

Лаунчер мультиплеера для **Minecraft PE 1.1.5**.

## Интерфейс (APK)

Тёмно-зелёная тема в стиле змеи:
- Вход / регистрация
- Список миров (карточки)
- Открыть свой мир
- Кнопка «Играть»

## Сборка APK (с телефона)

1. Зайди на GitHub → репозиторий `multiplayer-snake`
2. **Actions** → **Build APK** → **Run workflow**
3. Дождись окончания (15–40 мин)
4. Скачай artifact `multiplayer-snake-apk`
5. Установи APK на телефон

## Бэкенд

Папка `backend/` — Flask API. Нужен хостинг (Render) и `DATABASE_URL` (Neon).

В приложении API по умолчанию: `https://multiplayer-snake.onrender.com`  
(замени URL после деплоя на Render)

## Важно про Google Play

Google Play часто отклоняет неофициальные лаунчеры Minecraft.  
Может понадобиться публикация вне Play (сайт / Telegram) или сильная переработка под правила Google.
