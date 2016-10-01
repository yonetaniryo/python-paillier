#!/usr/bin/env python3

import datetime
import json

import click
import phe

__author__ = 'brian'


def log(m, color='red'):
    click.echo(click.style(m, fg=color), err=True)


@click.group("pheutil")
@click.version_option('1.0-alpha')
@click.option('--verbose', '-v', is_flag=True,
              help='Enables verbose mode.')
def cli(verbose=False):
    """CLI for interacting with python-paillier
    """

@cli.command("genpkey")
@click.argument('output', type=click.File('w'))
@click.option("--keysize", type=int, default=2048,
              help="The keysize in bits. Defaults to 2048")
@click.option("--id", type=str, default=None,
              help="Add an identifying comment to the key")
def generate_keypair(keysize, id, output):
    """Generate a paillier private key.

    Output as JWK to given output file. Use "-" to output the private key to
    stdout. See the extract command to extract the public component of the
    private key.

    Note:
        The default ID text includes the current time.
    """
    log("Generating a paillier keypair with keysize of {}".format(keysize))
    pub, priv = phe.generate_paillier_keypair(n_length=keysize)

    log("Keys generated")

    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    jwk_public = {
        'kty': "DAJ",
        'alg': "PAI-GN1",
        "key_ops": ["encrypt"],
        'n': phe.util.int_to_base64(pub.n),
        'kid': "Paillier public key generated by pheutil on {}".format(date)
    }

    jwk_private = {
        'kty': "DAJ",
        'key_ops': ["decrypt"],
        'lambda': phe.util.int_to_base64(priv.Lambda),
        'mu': phe.util.int_to_base64(priv.mu),
        'pub': jwk_public,
        'kid': "Paillier private key generated by pheutil on {}".format(date)
    }

    json.dump(jwk_private, output)
    output.write('\n')

    log("Private key written to {}".format(output.name))


@cli.command()
@click.argument('input', type=click.File('r'))
@click.argument('output', type=click.File('w'))
def extract(input, output):
    """Extract public key from private key.

    Given INPUT a private paillier key file as generated by generate, extract the
    public key portion to OUTPUT.

    Use "-" to output to stdout.
    """
    log("Loading paillier keypair")
    priv = json.load(input)
    error_msg = "Invalid private key"
    assert 'pub' in priv, error_msg
    assert priv['kty'] == 'DAJ', error_msg
    json.dump(priv['pub'], output)
    output.write('\n')
    log("Public key written to {}".format(output.name))



@cli.command()
@click.argument('public', type=click.File('r'))
@click.argument('plaintext', type=str)
@click.option('--output', type=click.File('w'),
              help="Save to file instead of stdout")
def encrypt(public, plaintext, output=None):
    """Encrypt a number with public key.

    The PLAINTEXT input will be interpreted as a floating point number.

    Output will be a JSON object with a "v" attribute containing the
    ciphertext as a string, and "e" the exponent as a Number,
    where possible fixed at -32.

    Note if you are passing a negative number to encrypt, you will
    need to include a "--" between the public key and your plaintext.
    """
    num = float(plaintext)

    log("Loading public key")
    publickeydata = json.load(public)
    pub = load_public_key(publickeydata)

    log("Encrypting: {:+.16f}".format(num))
    enc = pub.encrypt(num)
    serialised = serialise_encrypted(enc)
    # print(serialised, file=output)


def serialise_encrypted(enc):
    if enc.exponent > -32:
        enc = enc.decrease_exponent_to(-32)
        assert enc.exponent == -32
    else:
        log("Exponent is less than -32")

    obj = json.dumps({
        "v": str(enc.ciphertext()),
        "e": enc.exponent
    })
    return obj


@cli.command()
@click.argument('private', type=click.File('r'))
@click.argument('ciphertext', type=click.File('r'))
@click.option('--output', type=click.File('w'),
              help="Save to file instead of stdout")
def decrypt(private, ciphertext, output):
    """Decrypt ciphertext with private key.

    Requires PRIVATE key file and the CIPHERTEXT encrypted with
    the corresponding public key.
    """
    privatekeydata = json.load(private)
    assert 'pub' in privatekeydata
    pub = load_public_key(privatekeydata['pub'])

    log("Loading private key")
    private_key_error = "Invalid private key"
    assert 'key_ops' in privatekeydata, private_key_error
    assert "decrypt" in privatekeydata['key_ops'], private_key_error
    assert 'mu' in privatekeydata, private_key_error
    assert 'lambda' in privatekeydata, private_key_error
    assert privatekeydata['kty'] == 'DAJ', private_key_error

    _mu = phe.util.base64_to_int(privatekeydata['mu'])
    _lambda = phe.util.base64_to_int(privatekeydata['lambda'])

    private_key = phe.PaillierPrivateKey(pub, _lambda, _mu)

    log("Decrypting ciphertext")
    enc = load_encrypted_number(ciphertext, pub)
    out = private_key.decrypt(enc)
    # print(out, file=output)


@cli.command("addenc")
@click.argument('public', type=click.File('r'))
@click.argument('encrypted_a', type=click.File('r'))
@click.argument('encrypted_b', type=click.File('r'))
@click.option('--output', type=click.File('w'),
              help="Save to file instead of stdout")
def add_encrypted(public, encrypted_a, encrypted_b, output):
    """Add two encrypted numbers together.

    """
    log("Loading public key")
    publickeydata = json.load(public)
    pub = load_public_key(publickeydata)

    log("Loading first encrypted number")
    enc_a = load_encrypted_number(encrypted_a, pub)

    log("Loading second encrypted number")
    enc_b = load_encrypted_number(encrypted_b, pub)

    log("Adding encrypted numbers together")

    enc_result = enc_a + enc_b
    serialised_result = serialise_encrypted(enc_result)
    # print(serialised_result, file=output)


@cli.command("add")
@click.argument('public', type=click.File('r'))
@click.argument('encrypted', type=click.File('r'))
@click.argument('plaintext', type=str)
@click.option('--output', type=click.File('w'),
              help="Save to file instead of stdout")
def add_encrypted_to_plaintext(public, encrypted, plaintext, output):
    """Add encrypted number to unencrypted number.

    Requires a PUBLIC key file, a number ENCRYPTED with that public key
    also as a file, and the PLAINTEXT number to add.

    Creates a new encrypted number.
    """
    log("Loading public key")
    publickeydata = json.load(public)
    pub = load_public_key(publickeydata)

    log("Loading encrypted number")
    enc = load_encrypted_number(encrypted, pub)

    log("Loading unencrypted number")
    num = float(plaintext)

    log("Adding")
    enc_result = enc + num
    serialised_result = serialise_encrypted(enc_result)
    # print(serialised_result, file=output)


@cli.command("multiply")
@click.argument('public', type=click.File('r'))
@click.argument('encrypted', type=click.File('r'))
@click.argument('plaintext', type=str)
@click.option('--output', type=click.File('w'),
              help="Save to file instead of stdout")
def multiply_encrypted_to_plaintext(public, encrypted, plaintext, output):
    """Multiply encrypted num with unencrypted num.

    Requires a PUBLIC key file, a number ENCRYPTED with that public key
    also as a file, and the PLAINTEXT number to multiply.

    Creates a new encrypted number.
    """
    log("Loading public key")
    publickeydata = json.load(public)
    pub = load_public_key(publickeydata)

    log("Loading encrypted number")
    enc = load_encrypted_number(encrypted, pub)

    log("Loading unencrypted number")
    num = float(plaintext)

    log("Multiplying")
    enc_result = enc * num

    serialised_result = serialise_encrypted(enc_result)
    # print(serialised_result, file=output)


def load_public_key(public_key_data):
    error_msg = "Invalid public key"
    assert 'alg' in public_key_data, error_msg
    assert public_key_data['alg'] == 'PAI-GN1', error_msg
    assert public_key_data['kty'] == 'DAJ', error_msg

    n = phe.util.base64_to_int(public_key_data['n'])
    pub = phe.PaillierPublicKey(n+1, n)
    return pub


def load_encrypted_number(enc_number_file, pub):
    ciphertext_data = json.load(enc_number_file)
    assert 'v' in ciphertext_data
    assert 'e' in ciphertext_data

    enc = phe.EncryptedNumber(pub,
                              int(ciphertext_data['v']),
                              exponent=ciphertext_data['e']
                              )
    return enc


if __name__ == "__main__":
    cli()
