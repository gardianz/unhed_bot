# Unhedged FULL AUTO Signal Bot

Bot ini membaca market aktif BTC, SOL, dan ETH dari API Unhedged, menghitung metrik harga dari histori sebelum market close, lalu mengambil keputusan bet di jendela keputusan terakhir yang diatur lewat `.env`.

## Fitur

- Selector strategi lewat `SELECT_STRATEGY`
- Auto-discover market aktif jika `*_MARKET_ID` dikosongkan
- Freeze segment agar metrik yang sudah lewat tidak berubah lagi
- Live execution ke API Unhedged
- Event dan error notification ke Telegram jika diaktifkan
- Recovery pending bet saat bot restart

## Strategi

- `SELECT_STRATEGY=1`
  Strategi lama berbasis signed range.
- `SELECT_STRATEGY=2`
  Strategi baru berbasis absolut `high-low` per segmen M5.

Catatan:

- `BTC_AVG1_MIN`, `SOL_AVG1_MIN`, dan `ETH_AVG1_MIN` hanya dipakai oleh strategi `1`
- strategi `2` tidak memakai filter minimum `avg_1` per simbol

## Cara Install

1. Clone repository ini.
2. Masuk ke folder project.
3. Buat virtual environment.
4. Install dependency dari `requirements.txt`.
5. Salin `.env.example` menjadi `.env`.
6. Isi konfigurasi yang dibutuhkan.

Contoh di Windows PowerShell:

```powershell
git clone https://github.com/gardianz/unhed_bot.git
cd unhed_bot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Contoh di Linux/macOS:

```bash
git clone https://github.com/gardianz/unhed_bot.git
cd unhed_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Konfigurasi `.env`

Variable utama:

- `UNHEDGED_API_KEY`
  Wajib untuk live bet. Jangan commit ke Git.
- `UNHEDGED_API_BASE`
  Base URL API Unhedged.
- `SELECT_STRATEGY`
  `1` untuk strategi lama, `2` untuk strategi baru.
- `STAKE_CC`
  Nominal stake per order.
- `BOTH_STAKE_CC`
  Total stake khusus untuk signal `BOTH`. Nilai ini akan dibagi rata ke `YES` dan `NO`.
- `DECISION_WINDOW_SEC`
  Bet hanya dipertimbangkan saat sisa waktu kurang dari atau sama dengan nilai ini.

Timeout dan polling:

- `HTTP_CONNECT_TIMEOUT_SEC`
  Timeout saat membuka koneksi HTTP.
- `HTTP_TIMEOUT_SEC`
  Timeout baca response setelah koneksi tersambung.
- `POLL_INTERVAL_SEC`
  Jeda loop utama.
- `MARKET_DETAIL_REFRESH_SEC`
  Refresh detail market.
- `PRICE_HISTORY_REFRESH_SEC`
  Refresh histori harga.
- `RATE_LIMIT_BACKOFF_SEC`
  Backoff sementara saat kena rate limit.

Market selection:

- `BTC_MARKET_ID`
- `SOL_MARKET_ID`
- `ETH_MARKET_ID`

Fungsi `*_MARKET_ID`:

- Jika diisi, bot akan langsung memakai market ID tersebut.
- Jika dikosongkan, bot akan auto-discover market aktif dari API.
- Ini berguna kalau Anda ingin lock bot ke market tertentu dan mencegah auto-switch.

Filter strategi 1:

- `BTC_AVG1_MIN`
- `SOL_AVG1_MIN`
- `ETH_AVG1_MIN`

Telegram:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_TIMEOUT_SEC`
- `TELEGRAM_PREFIX`
- `TELEGRAM_LOG_LEVEL`
- `TELEGRAM_POSITION_UPDATE_SEC`

Telegram aktif hanya jika `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` diisi.

File output:

- `SIGNAL_HISTORY_PATH`
- `PENDING_BETS_PATH`

## Logic Strategi 1

Bot membagi histori harga menjadi 6 segmen tetap:

- seg1: `-30m` sampai `-25m`
- seg2: `-25m` sampai `-20m`
- seg3: `-20m` sampai `-15m`
- seg4: `-15m` sampai `-10m`
- seg5: `-10m` sampai `-5m`
- seg6: `-5m` sampai `-2m`

Setiap segmen dihitung dari `high - low` dengan arah:

- positif jika segmen ditutup naik
- negatif jika segmen ditutup turun
- nol jika segmen flat

Rumus:

- `average_1 = (seg1 + seg2 + seg3 + seg4 + seg5 + seg6) / 2`
- `average_2 = average_1 / 3`
- `range_1 = target price +- abs(average_1)`
- `range_2 = target price +- abs(average_2)`

Rule bet:

- jika `current price` ada di dalam `range_2` -> bet `BOTH`
- jika `current price` ada di atas `range_1` -> bet `YES`
- jika `current price` ada di bawah `range_1` -> bet `NO`
- jika harga ada di antara `range_2` dan `range_1` -> jangan bet

Filter tambahan:

- BTC: jika `abs(average_1) < BTC_AVG1_MIN` -> jangan bet
- SOL: jika `abs(average_1) < SOL_AVG1_MIN` -> jangan bet
- ETH: jika `abs(average_1) < ETH_AVG1_MIN` -> jangan bet
- pengecualian: kalau harga ada di dalam `range_2`, bot tetap boleh `BOTH`

## Logic Strategi 2

Strategi 2 memakai segmen:

- `seg_1`: sisa waktu 30 sampai 25 menit
- `seg_2`: sisa waktu 25 sampai 20 menit
- `seg_3`: sisa waktu 20 sampai 15 menit
- `seg_4`: sisa waktu 15 sampai 10 menit
- `seg_5`: sisa waktu 10 sampai 5 menit
- `seg_akhir`: sisa waktu 5 sampai 1 menit

Perhitungan:

- setiap nilai segmen memakai `abs(high - low)`
- `avg_1 = total_semua_segmen / jumlah_segmen`
- `avg_2 = avg_1 / 4`
- `selisih = abs(target_price - current_price)`

Rule bet:

- jika `selisih > avg_1` -> bet satu arah sesuai posisi harga terhadap target
- jika `selisih <= avg_2` -> bet `BOTH`
- jika `avg_2 < selisih <= avg_1` -> jangan bet

## Menjalankan Bot

```bash
python main.py
```

## Catatan Operasional

- `.env` sudah ada di `.gitignore`, jadi konfigurasi lokal dan API key tidak ikut ter-push.
- Jika startup terasa lama, biasanya bottleneck ada di request awal market discovery atau balance check.
- Jika API menolak bet, bot sekarang tetap hidup dan error akan dicatat ke log/event.
