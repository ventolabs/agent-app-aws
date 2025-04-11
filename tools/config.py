from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ENV = 'local'

class WavesSettings(BaseSettings):
    """Waves settings that can be set using environment variables."""
    model_config = SettingsConfigDict(
        env_prefix='WAVES_',
        case_sensitive=False,
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    waves_node: str = Field(default="https://nodes.wavesnodes.com", description="The Waves node URL")
    waves_chain: str = Field(default="mainnet", description="The Waves chain")
    waves_address: str = Field(default="3PAkXRMibqvwW5hXN2CTTWypVUYyDPsdgh6", description="The Waves address")
    waves_private_key: str|None = Field(default=None, description="The Waves private key")
    waves_mock_private_key: str|None = Field(default=None, description="The Waves mock private key")


class ToolsSettings(BaseSettings):
    """Tools settings that can be set using environment variables."""
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    waves: WavesSettings = WavesSettings()
    
    def is_local_env(self):
        return self.env == LOCAL_ENV
    
settings = ToolsSettings()


    