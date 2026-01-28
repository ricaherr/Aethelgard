"""
Encryption utilities for sensitive credential storage
Uses Fernet (symmetric encryption) from cryptography library
"""
import os
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


class CredentialEncryption:
    """Handles encryption/decryption of broker credentials"""
    
    def __init__(self, key_path: str = ".encryption_key"):
        self.key_path = Path(key_path)
        self._cipher = None
        self._load_or_generate_key()
    
    def _load_or_generate_key(self):
        """Load existing key or generate new one"""
        if self.key_path.exists():
            with open(self.key_path, 'rb') as f:
                key = f.read()
            logger.info("Loaded encryption key")
        else:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            # Set file permissions (owner read/write only)
            os.chmod(self.key_path, 0o600)
            logger.warning("⚠️ Generated NEW encryption key - BACKUP THIS FILE!")
        
        self._cipher = Fernet(key)
    
    def encrypt(self, value: str) -> bytes:
        """Encrypt a credential value"""
        if not isinstance(value, str):
            value = str(value)
        return self._cipher.encrypt(value.encode('utf-8'))
    
    def decrypt(self, encrypted_value: bytes) -> str:
        """Decrypt a credential value"""
        return self._cipher.decrypt(encrypted_value).decode('utf-8')
    
    def rotate_key(self, new_key_path: Optional[str] = None):
        """
        Rotate encryption key (for security)
        WARNING: Must re-encrypt all credentials after rotation
        """
        if new_key_path:
            self.key_path = Path(new_key_path)
        
        # Generate new key
        new_key = Fernet.generate_key()
        
        # Save old key as backup
        backup_path = self.key_path.with_suffix('.bak')
        if self.key_path.exists():
            self.key_path.rename(backup_path)
            logger.info(f"Old key backed up to {backup_path}")
        
        # Save new key
        with open(self.key_path, 'wb') as f:
            f.write(new_key)
        os.chmod(self.key_path, 0o600)
        
        self._cipher = Fernet(new_key)
        logger.warning("🔑 Encryption key rotated - re-encrypt all credentials!")


# Singleton instance
_encryption_instance = None

def get_encryptor() -> CredentialEncryption:
    """Get singleton encryption instance"""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = CredentialEncryption()
    return _encryption_instance
