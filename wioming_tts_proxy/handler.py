# --- START OF FILE handler.py ---
import logging
import asyncio

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.error import Error
from wyoming.info import Describe, Info, TtsProgram
from wyoming.tts import Synthesize
from wyoming.client import AsyncClient
from wyoming.server import AsyncEventHandler

from .normalizer import TextNormalizer

_LOGGER = logging.getLogger(__name__)

class TTSProxyEventHandler(AsyncEventHandler):
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        **kwargs
    ) -> None:
        self.proxy_program_info = kwargs.pop("proxy_program_info")
        self.cli_args = kwargs.pop("cli_args")
        self.upstream_tts_uri_for_logging = kwargs.pop("upstream_tts_uri_for_logging")
        self.upstream_tts_client_factory = kwargs.pop("upstream_tts_client_factory")
        self.text_normalizer = kwargs.pop("text_normalizer")
        
        super().__init__(reader, writer, **kwargs) 
        
        _LOGGER.info(f"TTSProxyEventHandler initialized. Upstream TTS for logging: {self.upstream_tts_uri_for_logging}")


    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            _LOGGER.debug("Received Describe event from client.")
            try:
                async with self.upstream_tts_client_factory() as upstream_client:
                    _LOGGER.debug(f"Sending Describe to upstream TTS: {self.upstream_tts_uri_for_logging}")
                    await upstream_client.write_event(Describe().event())
                    
                    upstream_response = await upstream_client.read_event()
                    if upstream_response and Info.is_type(upstream_response.type):
                        upstream_info = Info.from_event(upstream_response)
                        # ИСПРАВЛЕНО ЗДЕСЬ: используем .event().payload для логирования
                        _LOGGER.debug(f"Received Info from upstream TTS ({self.upstream_tts_uri_for_logging}): {upstream_info.event().payload}")

                        modified_tts_programs = []
                        if upstream_info.tts:
                            for prog in upstream_info.tts:
                                copied_voices = []
                                if prog.voices:
                                    for voice in prog.voices:
                                        copied_voices.append(voice)

                                new_prog = TtsProgram(
                                    name=f"{prog.name} (via {self.proxy_program_info['name']})",
                                    description=prog.description,
                                    attribution=prog.attribution,
                                    installed=prog.installed,
                                    version=prog.version,
                                    voices=copied_voices 
                                )
                                modified_tts_programs.append(new_prog)
                        
                        if not modified_tts_programs and upstream_info.tts is not None:
                             _LOGGER.warning(f"Upstream TTS ({self.upstream_tts_uri_for_logging}) provided TTS programs, but the list was empty or became empty.")
                        elif upstream_info.tts is None:
                             _LOGGER.warning(f"Upstream TTS ({self.upstream_tts_uri_for_logging}) did not provide any TTS programs (tts field was null).")

                        final_info_payload = { "tts": modified_tts_programs }
                        if upstream_info.asr: final_info_payload["asr"] = list(upstream_info.asr)
                        if upstream_info.handle: final_info_payload["handle"] = list(upstream_info.handle)
                        if upstream_info.intent: final_info_payload["intent"] = list(upstream_info.intent)
                        
                        final_info = Info(**final_info_payload)
                        await self.write_event(final_info.event())
                        _LOGGER.debug(f"Sent modified Info to client: {final_info.event().payload}")
                    else:
                        _LOGGER.warning(f"No Info event received from upstream TTS ({self.upstream_tts_uri_for_logging}) or unexpected event. Sending basic proxy info.")
                        basic_proxy_info_event = Info(tts=[TtsProgram(
                            name=self.proxy_program_info['name'], 
                            description=self.proxy_program_info['description'], 
                            voices=[]
                        )]).event()
                        await self.write_event(basic_proxy_info_event)
                        _LOGGER.debug(f"Sent basic proxy info as fallback: {basic_proxy_info_event.payload}")

            except ConnectionRefusedError:
                _LOGGER.error(f"Connection refused by upstream TTS ({self.upstream_tts_uri_for_logging}) for Describe.")
                await self.write_event(Error(text="Upstream TTS service is unavailable for Describe.").event())
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout connecting to upstream TTS ({self.upstream_tts_uri_for_logging}) for Describe.")
                await self.write_event(Error(text="Upstream TTS service timed out for Describe.").event())
            except Exception as e:
                _LOGGER.error(f"Error during Describe processing with upstream ({self.upstream_tts_uri_for_logging}): {e}", exc_info=True)
                await self.write_event(Error(text="Error getting info from upstream TTS.").event())
            return True

        if Synthesize.is_type(event.type):
            synthesize_event = Synthesize.from_event(event)
            original_text = synthesize_event.text
            
            normalized_text = self.text_normalizer.normalize(original_text)
            _LOGGER.info(f"Text for TTS (original): '{original_text[:50]}...' -> (normalized): '{normalized_text[:50]}...' Voice: {synthesize_event.voice}")

            if not normalized_text: 
                _LOGGER.warning("Text became empty after normalization.")
                sample_rate = 16000 
                sample_width = 2    
                channels = 1        
                await self.write_event(AudioStart(rate=sample_rate, width=sample_width, channels=channels).event())
                await self.write_event(AudioStop().event())
                _LOGGER.debug("Sent empty audio stream for empty normalized text.")
                return True
            
            proxied_synthesize_data = { "text": normalized_text }
            if synthesize_event.voice: 
                proxied_synthesize_data["voice"] = synthesize_event.voice
            if hasattr(synthesize_event, "data") and isinstance(synthesize_event.data, dict):
                for key, value in synthesize_event.data.items():
                    if key not in proxied_synthesize_data: 
                        proxied_synthesize_data[key] = value
            
            proxied_synthesize_event = Synthesize(**proxied_synthesize_data).event()
            _LOGGER.debug(f"Sending Synthesize to upstream ({self.upstream_tts_uri_for_logging}): {proxied_synthesize_event.payload}")

            try:
                async with self.upstream_tts_client_factory() as upstream_client: 
                    _LOGGER.debug(f"Connected to upstream TTS ({self.upstream_tts_uri_for_logging}). Sending Synthesize event.")
                    await upstream_client.write_event(proxied_synthesize_event)
                    
                    while True:
                        upstream_event = await upstream_client.read_event()
                        if upstream_event is None:
                            _LOGGER.warning(f"Upstream TTS ({self.upstream_tts_uri_for_logging}) connection closed or no more events.")
                            break 
                        _LOGGER.debug(f"Received event from upstream TTS ({self.upstream_tts_uri_for_logging}): {upstream_event.type}")
                        if AudioStart.is_type(upstream_event.type) or \
                           AudioChunk.is_type(upstream_event.type) or \
                           AudioStop.is_type(upstream_event.type) or \
                           Error.is_type(upstream_event.type):
                            await self.write_event(upstream_event)
                        else:
                            _LOGGER.warning(f"Received unexpected event type '{upstream_event.type}' from upstream TTS ({self.upstream_tts_uri_for_logging}). Ignoring.")
                        if AudioStop.is_type(upstream_event.type) or Error.is_type(upstream_event.type):
                            _LOGGER.debug(f"AudioStop or Error received from upstream ({self.upstream_tts_uri_for_logging}). Ending stream.")
                            break 
                    _LOGGER.info(f"Finished streaming audio from upstream TTS ({self.upstream_tts_uri_for_logging}).")
                _LOGGER.info("Finished processing Synthesize request.")
            except ConnectionRefusedError:
                _LOGGER.error(f"Connection refused by upstream TTS server ({self.upstream_tts_uri_for_logging}) for Synthesize")
                await self.write_event(Error(text="Upstream TTS service is unavailable.").event())
            except asyncio.TimeoutError:
                 _LOGGER.error(f"Timeout connecting to upstream TTS server ({self.upstream_tts_uri_for_logging}) for Synthesize")
                 await self.write_event(Error(text="Upstream TTS service timed out.").event())
            except Exception as e:
                _LOGGER.error(f"Error during communication with upstream TTS ({self.upstream_tts_uri_for_logging}): {e}", exc_info=True)
                await self.write_event(Error(text="An error occurred while communicating with the upstream TTS service.").event())
            return True 
        
        _LOGGER.warning(f"Received unhandled event type: {event.type}. Keeping connection open.")
        return True
# --- END OF FILE handler.py ---