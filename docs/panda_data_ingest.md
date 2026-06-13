# PandaData Ingest

`skills.ingest` is dedicated to PandaData/PandaAI access in the open-source
project.

## Setup

```bash
uv sync --extra panda_data
cp .env.example .env
```

Set:

```bash
PANDA_DATA_USERNAME=86xxxxxxxxxxx
PANDA_DATA_PASSWORD=your-password
```

## Daily Bars

```python
from skills.ingest import PandaDataClient

client = PandaDataClient()
df = client.fetch_market_data("SHSE.600000", "20230101", "20231231", type="stock")
```

## Save to QuantSpace Storage

```python
import pandas as pd

from skills.ingest import PandaDataClient
from skills.store.data_manager import DataManager

raw = PandaDataClient().fetch_market_data("SHSE.600000", "20230101", "20231231")
bars = raw.copy()
bars["eob"] = pd.to_datetime(bars["date"])
bars = bars.set_index("eob")[["open", "high", "low", "close", "volume"]].sort_index()

DataManager().save_symbol("SHSE.600000", bars, frequency="1d", source="panda_data")
```

## Symbol Conversion

```python
from skills.ingest import to_panda_data_symbol, to_quantspace_symbol

to_panda_data_symbol("SHSE.510300")   # "510300.SH"
to_quantspace_symbol("510300.SH")     # "SHSE.510300"
```
