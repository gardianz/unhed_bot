# Unhedged API Docs

## Authentication

Pass your API key as a Bearer token.

> Market listing endpoints are public and don't require auth.

```
Authorization: Bearer ak_your_key_here
```

**Base URL**

```
https://api.unhedged.gg
```

---

## 📌 GET /api/v1/markets

### PUBLIC — List Markets

Browse active prediction markets.
Public endpoint — no API key required.

### Query Parameters

| Parameter      | Type   | Description                                |
| -------------- | ------ | ------------------------------------------ |
| status         | string | ACTIVE | ENDED | RESOLVED | VOIDED         |
| category       | string | Filter by category                         |
| search         | string | Search query (max 200 chars)               |
| limit          | number | Results per page (1–100, default 20)       |
| offset         | number | Pagination offset (default 0)              |
| orderBy        | string | createdAt | endTime | totalPool | betCount |
| orderDirection | string | asc | desc                                 |

### Example

```bash
curl https://api.unhedged.gg/api/v1/markets
```

### Response

```json
{
  "markets": [
    {
      "id": "clx...",
      "question": "Will BTC hit $100k by June?",
      "status": "ACTIVE",
      "category": "Crypto",
      "outcomes": [
        { "index": 0, "label": "Yes" },
        { "index": 1, "label": "No" }
      ],
      "totalPool": "1500.0000000000",
      "endTime": "2026-06-01T00:00:00.000Z"
    }
  ],
  "total": 42,
  "activeCount": 12,
  "endedCount": 8,
  "resolvedCount": 22
}
```

---

## 📌 GET /api/v1/markets/:id

### PUBLIC — Get Market Details

Get full details for a single market including outcomes, pool sizes, and odds.

### Example

```bash
curl https://api.unhedged.gg/api/v1/markets/<market_id>
```

### Response

```json
{
  "market": {
    "id": "clx...",
    "question": "Will BTC hit $100k by June?",
    "description": "Resolves Yes if...",
    "status": "ACTIVE",
    "category": "Crypto",
    "outcomes": [
      { "index": 0, "label": "Yes" },
      { "index": 1, "label": "No" }
    ],
    "totalPool": "1500.0000000000",
    "endTime": "2026-06-01T00:00:00.000Z",
    "createdAt": "2026-01-15T..."
  }
}
```

---

## 📌 GET /api/v1/balance

### Get Balance

Check your current platform balance.

**Required scope:** `balance:read`

### Example

```bash
curl https://api.unhedged.gg/api/v1/balance \
  -H "Authorization: Bearer ak_your_key_here"
```

### Response

```json
{
  "balance": {
    "available": "500.0000000000",
    "lockedWithdraws": "0.0000000000",
    "lockedBets": "150.0000000000",
    "total": "650.0000000000",
    "totalDeposited": "1000.0000000000",
    "totalWithdrawn": "200.0000000000"
  },
  "withdrawalFee": "1.0000000000",
  "bettingFee": "0.0000000000",
  "ccPriceUsd": 0.015
}
```

---

## 📌 POST /api/v1/bets

### Place a Bet

Place a bet on a market outcome.

**Required scope:** `bet:place`

### Request Body

| Field          | Type   | Required | Description               |
| -------------- | ------ | -------- | ------------------------- |
| marketId       | string | ✅        | Market ID                 |
| outcomeIndex   | number | ✅        | Outcome index (0-based)   |
| amount         | number | ✅        | Amount in CC (min 0.0001) |
| idempotencyKey | string | ❌        | Prevent duplicate bets    |

### Example

```bash
curl -X POST https://api.unhedged.gg/api/v1/bets \
  -H "Authorization: Bearer ak_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "marketId": "clx...",
    "outcomeIndex": 0,
    "amount": 50
  }'
```

### Response

```json
{
  "bet": {
    "id": "clx...",
    "marketId": "clx...",
    "outcomeIndex": 0,
    "amount": "50.0000000000",
    "status": "CONFIRMED",
    "timeWeight": "1.0000"
  },
  "balanceAfter": "450.0000000000",
  "fee": "0.0000000000"
}
```

---

## 📌 GET /api/v1/bets

### List Your Bets

Retrieve your bet history.

**Required scope:** `bet:read`

### Query Parameters

| Parameter | Type   | Description                                 |
| --------- | ------ | ------------------------------------------- |
| status    | string | PENDING | CONFIRMED | WON | LOST | REFUNDED |
| marketId  | string | Filter by market                            |
| limit     | number | Results per page (1–100, default 20)        |
| offset    | number | Pagination offset                           |

### Example

```bash
curl https://api.unhedged.gg/api/v1/bets \
  -H "Authorization: Bearer ak_your_key_here"
```

### Response

```json
{
  "bets": [
    {
      "id": "clx...",
      "marketId": "clx...",
      "market": {
        "question": "Will BTC hit $100k?",
        "status": "ACTIVE",
        "outcomes": []
      },
      "outcomeIndex": 0,
      "amount": "50.0000000000",
      "status": "CONFIRMED",
      "createdAt": "2026-02-20T..."
    }
  ],
  "total": 5
}
```

---

## ❗ Error Codes

| Code | Description                                          |
| ---- | ---------------------------------------------------- |
| 400  | Bad request — invalid params or insufficient balance |
| 401  | Unauthorized — missing or invalid API key            |
| 403  | Forbidden — key doesn't have required scope          |
| 404  | Not found — market or bet doesn't exist              |
| 429  | Rate limited — slow down                             |
| 503  | Betting temporarily disabled by admin                |
