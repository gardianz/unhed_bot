# Unhedged FULL AUTO Signal Bot

Bot ini membaca market aktif BTC, SOL, dan ETH dari API Unhedged, menghitung range harga dari histori sebelum market close, lalu mengambil keputusan bet hanya di jendela keputusan terakhir yang bisa diatur dari `.env`.

## Logic

Bot membagi histori harga menjadi 6 segmen tetap:

- seg1: `-30m` sampai `-25m`
- seg2: `-25m` sampai `-20m`
- seg3: `-20m` sampai `-15m`
- seg4: `-15m` sampai `-10m`
- seg5: `-10m` sampai `-5m`
- seg6: `-5m` sampai `-2m`

Setiap segmen dihitung dari `high - low` pada rentang waktu itu, dengan arah:

- positif jika segmen ditutup naik
- negatif jika segmen ditutup turun
- nol jika segmen flat

Lalu bot menghitung:

- `average_1 = (seg1 + seg2 + seg3 + seg4 + seg5 + seg6) / 2`
- `average_2 = average_1 / 3`

Range keputusan dibentuk dari `target price` market:

- `range_1 = target price +- abs(average_1)`
- `range_2 = target price +- abs(average_2)`

Setiap segmen dibekukan begitu rentangnya lewat, jadi `high`, `low`, dan nilai signed range untuk segmen yang sudah selesai tidak boleh berubah lagi. Range final juga ikut tetap setelah semua 6 segmen selesai.

## Rule Bet

Keputusan hanya diambil saat `time left <= DECISION_WINDOW_SEC`.

- jika `current price` ada di dalam `range_2` -> bet `BOTH`
- jika `current price` ada di atas `range_1` -> bet `YES`
- jika `current price` ada di bawah `range_1` -> bet `NO`
- jika harga ada di antara `range_2` dan `range_1` -> jangan bet

Filter tambahan:

- BTC: jika `abs(average_1) < 70` -> jangan bet
- SOL: jika `abs(average_1) < 0.25` -> jangan bet
- ETH: jika `abs(average_1) < 2.55` -> jangan bet
- pengecualian: kalau harga ada di dalam `range_2`, bot tetap boleh `BOTH`

## UI

Tampilan terminal menunjukkan:

- total bet
- pnl berbasis perubahan balance saat ini terhadap balance awal
- target price
- current price
- time left
- delta target-current
- zone
- outcome
- your bet
- status
- avg_1
- avg_2
- range_1
- range_2
- segment `seg1..seg6`

## Konfigurasi

Salin `.env.example` ke `.env`, lalu isi:

- `UNHEDGED_API_KEY`: wajib untuk live bet
- `UNHEDGED_API_BASE`
- `STAKE_CC`
- `HTTP_TIMEOUT_SEC`
- `POLL_INTERVAL_SEC`
- `DECISION_WINDOW_SEC`
- `MARKET_DETAIL_REFRESH_SEC`
- `PRICE_HISTORY_REFRESH_SEC`
- `RATE_LIMIT_BACKOFF_SEC`
- `BTC_MARKET_ID`, `SOL_MARKET_ID`, `ETH_MARKET_ID`
- `BTC_AVG1_MIN`, `SOL_AVG1_MIN`, `ETH_AVG1_MIN`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` untuk kirim event ke Telegram
- `TELEGRAM_LOG_LEVEL` untuk warning/error logger ke Telegram
- `TELEGRAM_PREFIX` untuk header pesan Telegram

Kalau `*_MARKET_ID` dikosongkan, bot akan mencoba auto-discover market aktif dari API.

## Run

```bash
python main.py
```
