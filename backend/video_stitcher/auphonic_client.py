"""Auphonic API client for audio enhancement.

This module provides integration with the Auphonic API to enhance audio quality
by applying noise reduction, dehumming, volume leveling, and loudness normalization.
"""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


class AuphonicError(Exception):
    """Base exception for Auphonic API errors."""
    pass


class AuphonicAuthError(AuphonicError):
    """Authentication error with Auphonic API."""
    pass


class AuphonicUploadError(AuphonicError):
    """Error uploading file to Auphonic."""
    pass


class AuphonicProcessingError(AuphonicError):
    """Error during Auphonic processing."""
    pass


@dataclass
class AuphonicConfig:
    """Configuration for Auphonic API client."""
    api_token: str
    api_url: str = "https://auphonic.com/api"
    timeout: int = 300  # 5 minutes default timeout
    poll_interval: int = 5  # Poll every 5 seconds
    max_poll_attempts: int = 120  # Max 10 minutes polling (120 * 5s)
    
    # Audio enhancement settings
    # Enable/disable high-level features
    noise_reduction: bool = True
    dehumming: bool = True
    leveler: bool = True  # Volume leveling
    loudness_normalization: bool = True
    loudness_target: int = -16  # LUFS target for loudness normalization

    # Detailed algorithm tuning (Auphonic expects numeric choices/values)
    # denoisemethod: one of 'classic' (default), 'static', 'dynamic', 'speech_isolation'
    denoise_method: str = "dynamic"
    # denoiseamount: noise reduction amount in dB (0 = auto/default, -1 = off, 3/6/... are valid values)
    denoise_amount: int = 6

    # dehum: base frequency 0=auto, 50 or 60 for mains hum
    dehum_freq: int = 0
    # dehumamount: hum reduction amount in dB (0 = auto/default, -1 = off, 3/6/...)
    dehum_amount: int = 6

    # deverb (requires denoisemethod static, dynamic or speech_isolation)
    # deverbamount: 0 = auto (default), -1 = off, 3/6/... = amount in dB
    deverb_amount: int = 3

    # debreathamount (requires denoisemethod dynamic or speech_isolation)
    debreath_amount: int = 3
    
    # Output format
    output_format: str = "mp3"
    output_bitrate: int = 192  # kbps


class AuphonicClient:
    """Client for interacting with Auphonic API."""
    
    def __init__(self, config: AuphonicConfig):
        """Initialize Auphonic client.
        
        Args:
            config: Auphonic configuration.
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_token}",
            "User-Agent": "VideoStitcher/1.0"
        })
        logger.info("AuphonicClient initialized")
    
    def test_connection(self) -> bool:
        """Test connection to Auphonic API.
        
        Returns:
            True if connection successful, False otherwise.
        """
        try:
            response = self.session.get(
                f"{self.config.api_url}/user.json",
                timeout=10
            )
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Successfully connected to Auphonic API as: {user_data.get('data', {}).get('username', 'unknown')}")
                return True
            elif response.status_code == 401:
                logger.error("Auphonic API authentication failed. Check your API token.")
                return False
            else:
                logger.error(f"Auphonic API returned status code: {response.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Failed to connect to Auphonic API: {e}")
            return False
    
    def create_production(self, input_file: str) -> str:
        """Create a production (processing job) on Auphonic.
        
        Args:
            input_file: Path to input audio file (mp3 format).
            
        Returns:
            Production UUID.
            
        Raises:
            AuphonicAuthError: If authentication fails.
            AuphonicUploadError: If upload fails.
        """
        logger.info(f"Creating Auphonic production for: {input_file}")
        
        # Verify file exists
        if not Path(input_file).exists():
            raise AuphonicUploadError(f"Input file not found: {input_file}")
        
        try:
            # Step 1: Create production metadata
            # Build algorithms map using values that Auphonic expects.
            # Many Auphonic algorithm options expect specific choices/integers
            # (e.g. dehum expects 0/50/60, not a boolean). Map our boolean
            # config flags to valid API values here.
            algorithms: Dict[str, Any] = {}

            if self.config.noise_reduction:
                # Use configured denoise method and amount. Prefer 'dynamic' or
                # 'speech_isolation' for speech to get stronger results by default.
                algorithms["denoisemethod"] = self.config.denoise_method
                algorithms["denoiseamount"] = self.config.denoise_amount

            if self.config.dehumming:
                # dehum is the base frequency (0 = auto, 50 or 60 are valid choices)
                algorithms["dehum"] = self.config.dehum_freq
                algorithms["dehumamount"] = self.config.dehum_amount

            if self.config.leveler:
                # leveler: 0 = Auto (default), -1 = Off
                algorithms["leveler"] = 0

            if self.config.loudness_normalization:
                # normloudness: 0 = Auto (default), -1 = Off
                algorithms["normloudness"] = 0
                # loudness target is an integer LUFS value (e.g. -16)
                algorithms["loudnesstarget"] = self.config.loudness_target

            # De-reverb and de-breath adjustments (only include when configured)
            # deverbamount requires denoisemethod in ['static','dynamic','speech_isolation']
            if getattr(self.config, "deverb_amount", 0) and self.config.denoise_method in ["static", "dynamic", "speech_isolation"]:
                algorithms["deverbamount"] = self.config.deverb_amount

            # debreathamount requires denoisemethod in ['dynamic','speech_isolation']
            if getattr(self.config, "debreath_amount", 0) and self.config.denoise_method in ["dynamic", "speech_isolation"]:
                algorithms["debreathamount"] = self.config.debreath_amount

            production_data = {
                "metadata": {"title": Path(input_file).stem},
                "algorithms": algorithms,
                "output_files": [{
                    "format": self.config.output_format,
                    "bitrate": self.config.output_bitrate,
                }]
            }

            # Log the payload for debugging (do not include secrets)
            logger.debug(f"Creating production with payload: {production_data}")
            
            response = self.session.post(
                f"{self.config.api_url}/productions.json",
                json=production_data,
                timeout=30
            )
            
            if response.status_code == 401:
                raise AuphonicAuthError("Authentication failed. Check your API token.")
            
            if response.status_code not in [200, 201]:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error_message", "Unknown error")
                    # Log full error response for debugging
                    logger.error(f"Auphonic API error response: {error_data}")
                except Exception:
                    error_msg = response.text
                    logger.error(f"Auphonic API error (status {response.status_code}): {error_msg}")
                raise AuphonicUploadError(f"Failed to create production (HTTP {response.status_code}): {error_msg}")
            
            production_uuid = response.json()["data"]["uuid"]
            logger.info(f"Created production: {production_uuid}")
            
            # Step 2: Upload audio file
            logger.info(f"Uploading audio file ({Path(input_file).stat().st_size / 1024 / 1024:.2f} MB)...")
            
            with open(input_file, 'rb') as f:
                files = {'input_file': (Path(input_file).name, f, 'audio/mpeg')}
                upload_response = self.session.post(
                    f"{self.config.api_url}/production/{production_uuid}/upload.json",
                    files=files,
                    timeout=self.config.timeout
                )
            
            if upload_response.status_code not in [200, 201]:
                error_msg = upload_response.json().get("error_message", "Unknown error")
                raise AuphonicUploadError(f"Failed to upload file: {error_msg}")
            
            logger.info("Audio file uploaded successfully")
            return production_uuid
            
        except requests.RequestException as e:
            raise AuphonicUploadError(f"Network error during upload: {e}")
    
    def start_production(self, production_uuid: str) -> None:
        """Start processing a production.
        
        Args:
            production_uuid: Production UUID to start.
            
        Raises:
            AuphonicProcessingError: If starting production fails.
        """
        logger.info(f"Starting production: {production_uuid}")
        
        try:
            response = self.session.post(
                f"{self.config.api_url}/production/{production_uuid}/start.json",
                timeout=30
            )
            
            if response.status_code not in [200, 201]:
                error_msg = response.json().get("error_message", "Unknown error")
                raise AuphonicProcessingError(f"Failed to start production: {error_msg}")
            
            logger.info("Production started successfully")
            
        except requests.RequestException as e:
            raise AuphonicProcessingError(f"Network error starting production: {e}")
    
    def get_production_status(self, production_uuid: str) -> Dict[str, Any]:
        """Get the status of a production.
        
        Args:
            production_uuid: Production UUID.
            
        Returns:
            Production status data.
            
        Raises:
            AuphonicProcessingError: If status check fails.
        """
        try:
            response = self.session.get(
                f"{self.config.api_url}/production/{production_uuid}.json",
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = response.json().get("error_message", "Unknown error")
                raise AuphonicProcessingError(f"Failed to get production status: {error_msg}")
            
            return response.json()["data"]
            
        except requests.RequestException as e:
            raise AuphonicProcessingError(f"Network error checking status: {e}")
    
    def wait_for_completion(self, production_uuid: str, progress_callback: Optional[callable] = None) -> None:
        """Wait for production to complete processing.
        
        Args:
            production_uuid: Production UUID.
            progress_callback: Optional callback function(status, message).
            
        Raises:
            AuphonicProcessingError: If processing fails or times out.
        """
        logger.info(f"Waiting for production {production_uuid} to complete...")
        
        attempts = 0
        while attempts < self.config.max_poll_attempts:
            try:
                status_data = self.get_production_status(production_uuid)
                status = status_data.get("status_string", "Unknown")
                
                logger.debug(f"Production status: {status}")
                
                if progress_callback:
                    progress_callback(status, f"Audio enhancement: {status}")
                
                if status == "Done":
                    logger.info("Production completed successfully")
                    return
                elif status == "Error":
                    error_msg = status_data.get("error_message", "Unknown error")
                    raise AuphonicProcessingError(f"Production failed: {error_msg}")
                elif status in ["Waiting", "Processing", "Encoding", "Uploading"]:
                    # Still processing
                    time.sleep(self.config.poll_interval)
                    attempts += 1
                else:
                    # Unknown status
                    logger.warning(f"Unknown production status: {status}")
                    time.sleep(self.config.poll_interval)
                    attempts += 1
                    
            except AuphonicProcessingError:
                raise
            except Exception as e:
                logger.error(f"Error polling production status: {e}")
                time.sleep(self.config.poll_interval)
                attempts += 1
        
        raise AuphonicProcessingError(
            f"Production timed out after {self.config.max_poll_attempts * self.config.poll_interval} seconds"
        )
    
    def download_result(self, production_uuid: str, output_path: str) -> str:
        """Download the processed audio file.
        
        Args:
            production_uuid: Production UUID.
            output_path: Path where to save the output file.
            
        Returns:
            Path to downloaded file.
            
        Raises:
            AuphonicProcessingError: If download fails.
        """
        logger.info(f"Downloading enhanced audio to: {output_path}")
        
        try:
            # Get production details to find download URL
            status_data = self.get_production_status(production_uuid)
            
            if not status_data.get("output_files"):
                raise AuphonicProcessingError("No output files available")
            
            download_url = status_data["output_files"][0]["download_url"]
            
            # Download file
            response = self.session.get(download_url, stream=True, timeout=self.config.timeout)
            
            if response.status_code != 200:
                raise AuphonicProcessingError(f"Failed to download file: HTTP {response.status_code}")
            
            # Save to file
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = output_file.stat().st_size / 1024 / 1024
            logger.info(f"Downloaded enhanced audio ({file_size:.2f} MB)")
            
            return str(output_file)
            
        except requests.RequestException as e:
            raise AuphonicProcessingError(f"Network error downloading result: {e}")
    
    def enhance_audio(
        self,
        input_file: str,
        output_file: str,
        progress_callback: Optional[callable] = None
    ) -> str:
        """Complete workflow to enhance audio file.
        
        This is the main public API that combines all steps:
        1. Create production
        2. Upload audio
        3. Start processing
        4. Wait for completion
        5. Download result
        
        Args:
            input_file: Path to input audio file (mp3).
            output_file: Path where to save enhanced audio.
            progress_callback: Optional callback function(status, message).
            
        Returns:
            Path to enhanced audio file.
            
        Raises:
            AuphonicError: If any step fails.
        """
        logger.info("=" * 60)
        logger.info("AUPHONIC AUDIO ENHANCEMENT")
        logger.info("=" * 60)
        logger.info(f"Input:  {input_file}")
        logger.info(f"Output: {output_file}")
        
        start_time = time.time()
        
        try:
            # Step 1: Create production and upload
            if progress_callback:
                progress_callback("uploading", "Uploading audio to Auphonic...")
            production_uuid = self.create_production(input_file)
            
            # Step 2: Start processing
            if progress_callback:
                progress_callback("processing", "Starting audio enhancement...")
            self.start_production(production_uuid)
            
            # Step 3: Wait for completion
            self.wait_for_completion(production_uuid, progress_callback)
            
            # Step 4: Download result
            if progress_callback:
                progress_callback("downloading", "Downloading enhanced audio...")
            result_path = self.download_result(production_uuid, output_file)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Audio enhancement completed in {elapsed_time:.2f}s")
            logger.info("=" * 60)
            
            return result_path
            
        except AuphonicError as e:
            logger.error(f"Auphonic enhancement failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during audio enhancement: {e}")
            raise AuphonicError(f"Unexpected error: {e}")


def get_auphonic_client_from_env() -> Optional[AuphonicClient]:
    """Create Auphonic client from environment variables.
    
    Reads AUPHONIC_API_TOKEN from environment.
    
    Returns:
        AuphonicClient instance if token is set, None otherwise.
    """
    api_token = os.getenv("AUPHONIC_API_TOKEN")
    
    if not api_token:
        logger.warning("AUPHONIC_API_TOKEN not set in environment")
        return None
    
    config = AuphonicConfig(api_token=api_token)
    client = AuphonicClient(config)
    
    # Test connection
    if not client.test_connection():
        logger.error("Failed to connect to Auphonic API")
        return None
    
    return client
