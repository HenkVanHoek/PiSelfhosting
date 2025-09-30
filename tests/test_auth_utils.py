# tests/test_auth_utils.py

from passlib.hash import bcrypt

from src.utils.auth_utils import generate_basic_auth_hash


def test_generate_basic_auth_hash_creates_valid_bcrypt_output():
    """
    Test that the function generates a securely hashed string in the
    'username:hash' format using the bcrypt algorithm.
    """
    username = "testuser"
    password = "SecurePassword123"

    # Call the function under test
    result_string = generate_basic_auth_hash(username, password)

    # 1. Assert the format: should be 'username:hash'
    assert result_string.startswith(f"{username}:")
    assert ":" in result_string

    # Unpack the result: (username, hash_string)
    # The new directive requires unpacking
    parts = result_string.split(":", 1)
    unpacked_username, hash_string = parts

    # 2. Assert the hash itself is a valid bcrypt hash
    # (i.e., starts with $2y$ or $2b$)
    assert hash_string.startswith("$2y$") or hash_string.startswith("$2b$")

    # 3. Assert the hash is verifiable (the core security test)
    # Use passlib's bcrypt verification method
    assert bcrypt.verify(password, hash_string)


def test_generate_basic_auth_hash_is_unique_on_each_call():
    """
    Test that calling the function twice with the same input yields two
    DIFFERENT hashes, verifying that a unique salt is generated.
    """
    username = "testuser"
    password = "SecurePassword123"

    hash_one = generate_basic_auth_hash(username, password)
    hash_two = generate_basic_auth_hash(username, password)

    # The result strings must be different because bcrypt uses a random salt
    assert hash_one != hash_two

    # But both must still verify against the original password
    parts_one = hash_one.split(":", 1)
    parts_two = hash_two.split(":", 1)

    # Defensive unpacking check for the core assertion
    hash_one_string = next(iter(parts_one[1:]), None)
    hash_two_string = next(iter(parts_two[1:]), None)

    assert hash_one_string is not None
    assert hash_two_string is not None

    assert bcrypt.verify(password, hash_one_string)
    assert bcrypt.verify(password, hash_two_string)
