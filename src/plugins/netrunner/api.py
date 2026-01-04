from os import path
from requests import Response, get
from time import sleep
from re import sub
from unicodedata import normalize, category

NETRUNNERDB_URL_TEMPLATE = (
    "https://api-preview.netrunnerdb.com/api/v3/public/cards/{card_name}"
)
NRO_PROXY_URL_TEMPLATE = "https://nro-public.s3.nl-ams.scw.cloud/nro/card-printings/v2/webp/english/card/{print_id}.webp"

OUTPUT_CARD_ART_FILE_TEMPLATE = "{deck_index}{card_name}{quantity_counter}.png"


def request_api(query: str) -> Response:
    r = get(query, headers={"user-agent": "silhouette-card-maker/0.1", "accept": "*/*"})

    r.raise_for_status()
    sleep(0.15)

    return r


def fetch_card(
    index: int,
    quantity: int,
    name: str,
    front_img_dir: str,
):
    # Query for card info
    # Query for a normalized name of Latin scripts
    sanitized = sub(
        r"[^A-Za-z0-9 \-]+",
        "",
        "".join(c for c in normalize("NFD", name) if category(c) != "Mn"),
    )
    slugified = sub(r"\s+|-", "_", sanitized).lower()
    json = request_api(NETRUNNERDB_URL_TEMPLATE.format(card_name=slugified)).json()

    if isinstance(json.get("data"), list) is True:
        raise ValueError(f'Could not parse data for card "{name}"')

    # Get the latest printing id
    latest_print_id = json.get("data").get("attributes").get("latest_printing_id")
    card_art = request_api(
        NRO_PROXY_URL_TEMPLATE.format(print_id=latest_print_id)
    ).content

    if card_art is not None:
        # Save image based on quantity
        for counter in range(quantity):
            image_path = path.join(
                front_img_dir,
                OUTPUT_CARD_ART_FILE_TEMPLATE.format(
                    deck_index=str(index),
                    card_name=name,
                    quantity_counter=str(counter + 1),
                ),
            )

            with open(image_path, "wb") as f:
                f.write(card_art)


def get_handle_card(
    front_img_dir: str,
):
    def configured_fetch_card(index: int, name: str, quantity: int = 1):
        fetch_card(index, quantity, name, front_img_dir)

    return configured_fetch_card
