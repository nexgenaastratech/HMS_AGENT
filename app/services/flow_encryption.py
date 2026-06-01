import os
import json
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

# Load Private Key from Env
PRIVATE_KEY_PEM = os.getenv("PRIVATE_KEY")

def decrypt_request(encrypted_flow_data_b64, encrypted_aes_key_b64, initial_vector_b64):
    try:
        # 1. Parse Input
        flow_data = base64.b64decode(encrypted_flow_data_b64)
        encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)
        iv = base64.b64decode(initial_vector_b64)

        # Clean up PEM format if needed (handle newlines)
        formatted_key = PRIVATE_KEY_PEM.replace('\\n', '\n').strip()
        
        # DEBUG: Check if it looks like a private key
        if "PUBLIC KEY" in formatted_key:
             print("❌ CRITICAL ERROR: You put a PUBLIC KEY in the Private Key environment variable!")
             return None, None, None, "CRITICAL: You put a PUBLIC KEY in the Private Key env var!"
             
        try:
            private_key = serialization.load_pem_private_key(
                formatted_key.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Log Fingerprint helps verify which key is active without exposing it
            idx_bytes = private_key.private_bytes(
                 encoding=serialization.Encoding.DER,
                 format=serialization.PrivateFormat.PKCS8,
                 encryption_algorithm=serialization.NoEncryption()
            )
            digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
            digest.update(idx_bytes)
            fingerprint = digest.finalize().hex()[:8]
            print(f"🔑 Loaded Private Key Fingerprint: {fingerprint}...")

        except Exception as key_err:
            print(f"❌ Key Loading Failed: {key_err}")
            print(f"   Key Start: {formatted_key[:20]}...")
            return None, None, None, f"Key Loading Failed: {key_err}"

        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # 3. Decrypt Flow Data with AES Key (GCM Mode)
        # Authentication tag is the last 16 bytes of the encrypted data
        encrypted_data = flow_data[:-16]
        auth_tag = flow_data[-16:]

        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(iv, auth_tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted_data_bytes = decryptor.update(encrypted_data) + decryptor.finalize()

        decrypted_json = json.loads(decrypted_data_bytes.decode('utf-8'))
        return decrypted_json, aes_key, iv, None

    except Exception as e:
        error_msg = f"Decryption Error: {str(e)}"
        print(f"❌ {error_msg}")
        # Identify if it's an AES-GCM (Tag check) failure -> Wrong Aes Key -> Wrong Private Key
        if "Tag mismatch" in str(e):
             hint = "👉 CAUSE: Tag Mismatch. Private Key on Server != Public Key in Meta."
             print(hint)
             error_msg += f" || {hint}"
        return None, None, None, error_msg

def encrypt_response(response_data, aes_key, iv):
    try:
        # 1. Flip IV for response (standard procedure)
        # We need to create a NEW IV for the response, usually by flipping bits or standard mechanism.
        # However, Meta documentation says: "Use the same AES key and IV used to decrypt the request." 
        # BUT check documentation: usually requires a new IV or specific handling.
        # STANDARD FLOW: The response uses the SAME AES Key but a FLIPPED IV.
        
        iv_bytes = bytearray(iv)
        for i in range(len(iv_bytes)):
            iv_bytes[i] ^= 0xFF # Invert bits
        inverted_iv = bytes(iv_bytes)

        # 2. Encrypt Response JSON
        json_data = json.dumps(response_data).encode('utf-8')
        
        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(inverted_iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(json_data) + encryptor.finalize()
        auth_tag = encryptor.tag

        # 3. Combine Encrypted Data + Tag
        encrypted_blob = encrypted_data + auth_tag
        return base64.b64encode(encrypted_blob).decode('utf-8')

    except Exception as e:
        print(f"❌ Encryption Error: {e}")
        return None
