# src/utils/auth_utils.py

from passlib.hash import bcrypt

# Define the rounds for bcrypt to ensure secure generation (default is 12)
# Using a fixed, strong default for stability and security.
BCRYPT_ROUNDS = 12


def generate_basic_auth_hash(username: str, password: str) -> str:
    """
    Generates a username:hashed_password string suitable for Traefik and
    other basic authentication systems using the bcrypt algorithm.

    The password hash is generated using passlib's bcrypt with a secure
    default number of rounds.

    Args:
        username: The user's plaintext username.
        password: The user's plaintext password.

    Returns:
        A string in the format "username:hash" where hash is a bcrypt hash.
    """
    # 1. Generate the secure hash using passlib's bcrypt.
    hashed_password = bcrypt.using(rounds=BCRYPT_ROUNDS).hash(password)

    # 2. Return the result in the required Traefik/htpasswd format.
    return f"{username}:{hashed_password}"
