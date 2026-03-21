diff --git a/c:\Users\gosjavar\Documents\projek gabut\unhedged\README.md b/c:\Users\gosjavar\Documents\projek gabut\unhedged\README.md
new file mode 100644
--- /dev/null
+++ b/c:\Users\gosjavar\Documents\projek gabut\unhedged\README.md
@@ -0,0 +1,86 @@
+# Unhedged FULL AUTO Signal Bot
+
+Bot ini membaca market aktif BTC, SOL, dan ETH dari API Unhedged, menghitung range harga dari histori sebelum market close, lalu mengambil keputusan bet hanya di 1 menit terakhir.
+
+## Logic
+
+Bot membagi histori harga menjadi 4 segmen tetap:
+
+- seg1: `-21m` sampai `-16m`
+- seg2: `-16m` sampai `-11m`
+- seg3: `-11m` sampai `-6m`
+- seg4: `-6m` sampai `-3m`
+
+Setiap segmen dihitung dari `high - low` pada rentang waktu itu, dengan arah:
+
+- positif jika segmen ditutup naik
+- negatif jika segmen ditutup turun
+- nol jika segmen flat
+
+Lalu bot menghitung:
+
+- `average_1 = (seg1 + seg2 + seg3 + seg4) / 2`
+- `average_2 = average_1 / 3`
+
+Range keputusan dibentuk dari `target price` market:
+
+- `range_1 = target price +- abs(average_1)`
+- `range_2 = target price +- abs(average_2)`
+
+Range ini dibekukan saat masuk masa jeda, jadi tidak berubah lagi di menit keputusan.
+
+## Rule Bet
+
+Keputusan hanya diambil saat `time left <= 1 menit`.
+
+- jika `current price` ada di dalam `range_2` -> bet `BOTH`
+- jika `current price` ada di atas `range_1` -> bet `YES`
+- jika `current price` ada di bawah `range_1` -> bet `NO`
+- jika harga ada di antara `range_2` dan `range_1` -> jangan bet
+
+Filter tambahan:
+
+- BTC: jika `abs(average_1) < 70` -> jangan bet
+- SOL: jika `abs(average_1) < 0.25` -> jangan bet
+- ETH: jika `abs(average_1) < 2.55` -> jangan bet
+- pengecualian: kalau harga ada di dalam `range_2`, bot tetap boleh `BOTH`
+
+## UI
+
+Tampilan terminal menunjukkan:
+
+- total bet
+- pnl berbasis perubahan balance saat ini terhadap balance awal
+- target price
+- current price
+- time left
+- delta target-current
+- zone
+- outcome
+- your bet
+- status
+- avg_1
+- avg_2
+- range_1
+- range_2
+- segment `m5/m5/m5/m3`
+
+## Konfigurasi
+
+Salin `.env.example` ke `.env`, lalu isi:
+
+- `UNHEDGED_API_KEY`: wajib untuk live bet
+- `UNHEDGED_API_BASE`
+- `STAKE_CC`
+- `HTTP_TIMEOUT_SEC`
+- `POLL_INTERVAL_SEC`
+- `BTC_MARKET_ID`, `SOL_MARKET_ID`, `ETH_MARKET_ID`
+- `BTC_AVG1_MIN`, `SOL_AVG1_MIN`, `ETH_AVG1_MIN`
+
+Kalau `*_MARKET_ID` dikosongkan, bot akan mencoba auto-discover market aktif dari API.
+
+## Run
+
+```bash
+python main.py
+```
