# Telegram Stars Media Bot

## Railway Variables — միայն 2 հատ

- `BOT_TOKEN` — BotFather token
- `ADMIN_ID` — քո Telegram numeric ID-ն

Ուրիշ Environment Variable պետք չէ։ Railway-ի `PORT`-ը օգտագործվում է ավտոմատ, իսկ եթե այն չլինի՝ կօգտագործվի 8080։

## Հնարավորություններ

- `/start` → կատալոգ
- 0 Stars → անվճար
- 1–10000 Stars → Telegram Stars վճարում
- 🎬 վիդեոներ
- 🖼️ նկարներ
- 📝 վերնագիր + նկարագրություն
- 👑 Telegram Web App Admin Panel
- ➕ ավելացնել նյութ
- 🗑️ ջնջել նյութ
- 📊 օգտատերերի, գնումների և Stars-ի վիճակագրություն
- JSON storage, SQLite չկա

## Deploy

1. ZIP-ը բացիր։
2. Ֆայլերը Railway-ում deploy արա։
3. Variables-ում գրիր միայն `BOT_TOKEN` և `ADMIN_ID`։
4. Railway → Settings/Networking → ստեղծիր Public Domain։
5. Բոտում ուղարկիր `/admin`։
6. Բացված Telegram Web App-ից կառավարիր նյութերը։

## Նյութ ավելացնել

1. Բոտին ուղարկիր `/getid`։
2. Ուղարկիր վիդեոն կամ նկարը։
3. Բոտը կտա Telegram `file_id`։
4. `/admin` → Add media։
5. Ընտրիր video/photo։
6. Տեղադրիր file_id։
7. Գրիր վերնագիր, նկարագրություն և 0–10000 Stars գին։

## Տվյալներ

SQLite ընդհանրապես չկա։ Տվյալները պահվում են `data/media.json`, `data/users.json`, `data/purchases.json` ֆայլերում։

Եթե Railway-ում redeploy-ից հետո տվյալների պահպանումը կարևոր է, միացրու Railway Volume և mount արա `/app/data`-ում։ Դա նոր Environment Variable չի պահանջում։

## BotFather commands

`start` - Սկսել
`admin` - Admin Panel
`getid` - Ստանալ media file_id
