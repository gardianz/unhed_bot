# Unhedged FULL AUTO Signal Bot

Bot ini membaca market aktif dari API Unhedged, lalu menghasilkan sinyal berdasarkan selisih `current price` terhadap `target price` market.

Trigger bawaan:

- BTC: `BOTH` di `+-100`, directional `YES` di `+300`, directional `NO` di `-300`
- SOL: `BOTH` di `+-0.15`, directional `YES` di `+0.5`, directional `NO` di `-0.5`
- ETH: `BOTH` di `+-3`, directional `YES` di `+10`, directional `NO` di `-10`

## Konfigurasi

Salin `.env.example` ke `.env`, lalu isi:

- `UNHEDGED_API_KEY`: wajib untuk live bet
- `BTC_MARKET_ID`, `SOL_MARKET_ID`, `ETH_MARKET_ID`: opsional, kalau kosong bot akan coba cari market aktif dari API
- `STAKE_CC`, `WATCH_THRESHOLD_MIN`, `HTTP_TIMEOUT_SEC`, `POLL_INTERVAL_SEC`
- `BTC_BOTH_DELTA`, `BTC_DIRECTIONAL_DELTA`, `SOL_BOTH_DELTA`, `SOL_DIRECTIONAL_DELTA`, `ETH_BOTH_DELTA`, `ETH_DIRECTIONAL_DELTA`

## Run

```bash
python main.py
```
