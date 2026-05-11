# Oslo Trafikk

AI-drevet trafikkprediksjon for Oslo basert på data fra Statens Vegvesen og MET Norge.

## Funksjoner
- Kart over Oslo med fargelagte veier (gronn/gul/rod/lilla) basert på predikert ko
- Tidsslider for a se ko-prediksjon time for time
- Sammenligning av bil vs kollektivtransport
- Modell trent pa historiske trafikkdata + vaerdata

## Kom i gang

pip install -r requirements.txt
python scripts/fetch_historical.py
python model/train.py
uvicorn api.main:app --reload

## Datakilder
- Statens Vegvesen Trafikkdata API
- MET Norge Locationforecast API
- Entur Journey Planner API