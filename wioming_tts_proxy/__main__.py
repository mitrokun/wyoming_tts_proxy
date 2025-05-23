# --- START OF FILE __main__.py ---
import os
import asyncio
import logging
import sys
from functools import partial
from argparse import ArgumentParser

from wyoming.info import Attribution, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncServer
from wyoming.client import AsyncClient
# from wyoming.event import Event

from .handler import TTSProxyEventHandler
from .normalizer import TextNormalizer


PROXY_PROGRAM_NAME = "normalizing-tts-proxy"
PROXY_PROGRAM_DESCRIPTION = "Wyoming TTS proxy with text normalization"
PROXY_PROGRAM_VERSION = "0.1.0"
PROXY_ATTRIBUTION_NAME = "My TTS Proxy"
PROXY_ATTRIBUTION_URL = "https://github.com/your-repo"

_LOGGER = logging.getLogger(__name__)

def create_upstream_tts_client(uri: str) -> AsyncClient:
    return AsyncClient.from_uri(uri)

async def main() -> None:
    logging.basicConfig(level=os.getenv("LOGLEVEL", "INFO").upper(),
                        format='%(asctime)s %(levelname)s %(name)s %(module)s: %(message)s')

    parser = ArgumentParser(description=PROXY_PROGRAM_DESCRIPTION)
    parser.add_argument(
        "--uri",
        default="tcp://0.0.0.0:10201",
        help="unix:// or tcp:// URI where this proxy server will listen"
    )
    parser.add_argument(
        "--upstream-tts-uri",
        required=True,
        help="unix:// or tcp:// URI of the upstream Wyoming TTS service (e.g., your Vosk TTS)"
    )
    args = parser.parse_args()

    _LOGGER.info(f"Starting {PROXY_PROGRAM_NAME} v{PROXY_PROGRAM_VERSION}")
    _LOGGER.info(f"Proxy will listen on: {args.uri}")
    _LOGGER.info(f"Upstream TTS service: {args.upstream_tts_uri}")

    text_normalizer = TextNormalizer()

    proxy_program_basic_info = {
        "name": PROXY_PROGRAM_NAME,
        "description": PROXY_PROGRAM_DESCRIPTION,
        "version": PROXY_PROGRAM_VERSION,
        "attribution_name": PROXY_ATTRIBUTION_NAME,
        "attribution_url": PROXY_ATTRIBUTION_URL,
    }

    upstream_tts_client_factory = partial(create_upstream_tts_client, args.upstream_tts_uri)

    handler_factory = partial(
        TTSProxyEventHandler,
        proxy_program_info=proxy_program_basic_info,
        cli_args=args, # Оставляем cli_args, если он нужен для чего-то еще
        upstream_tts_uri_for_logging=args.upstream_tts_uri, # <--- ДОБАВЛЕНО для логирования
        upstream_tts_client_factory=upstream_tts_client_factory,
        text_normalizer=text_normalizer,
    )

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info(f"Proxy server ready and listening at {args.uri}")

    try:
        await server.run(handler_factory)
    except OSError as e:
        _LOGGER.error(f"Failed to start server at {args.uri}: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        _LOGGER.info("Server shutting down due to KeyboardInterrupt.")
    finally:
        _LOGGER.info("Proxy server has shut down.")

if __name__ == "__main__":
    asyncio.run(main())
# --- END OF FILE __main__.py ---