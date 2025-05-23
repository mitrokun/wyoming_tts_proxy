# wyoming tts proxy
Draft. Removing asterisks from text.

### Run
`python -m wioming_tts_proxy --uri tcp://0.0.0.0.0:10201 --upstream-tts-uri tcp://127.0.0.0.1:10200
`

If you change the tts engine, it requires reload the integration to update the data.

All necessary text manipulations are performed in `normalizer.py`

Inspired by [Wyoming RapidFuzz Proxy](https://github.com/Cheerpipe/wyoming_rapidfuzz_proxy)
