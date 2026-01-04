#!/usr/bin/env python3
"""
SLD Collector Number Range Mapping

Maps collector number ranges to official drop names.
This allows accurate organization when multiple drops share the same release date.

Source: https://scryfall.com/sets/sld
"""

# Format: (min_collector, max_collector, "drop-name")
# Ranges are inclusive
SLD_COLLECTOR_RANGES = [
    # 2019
    (1, 5, "bitterblossom-dreams"),
    (6, 8, "restless-in-peace"),
    (9, 11, "kaleidoscope-killers"),
    (12, 16, "year-of-the-rat"),
    (17, 21, "explosion-sounds"),
    (22, 28, "omg-kitties"),
    (29, 32, "seeing-visions"),
    (33, 36, "year-of-the-rat"),
    # 2020
    (37, 40, "thalia-beyond-the-helvault"),
    (41, 45, "full-sleeves-the-tattoo-pack"),
    (46, 50, "the-tokyo-lands"),
    (51, 55, "international-womens-day"),
    (56, 58, "can-you-feel-with-a-heart-of-steel"),
    (59, 537, "spooky-superdrop"),  # Large range
    (60, 62, "april-fools"),
    (63, 67, "the-godzilla-lands"),
    (68, 82, "theros-stargazing"),
    (83, 86, "mountain-go"),
    (87, 90, "the-path-not-traveled"),
    (91, 95, "ornithological-studies"),
    (96, 99, "every-dog-has-its-day"),
    (100, 109, "happy-little-gathering"),
    (110, 114, "happy-yargle-day"),
    (115, 118, "faerie-faerie-faerie-rad"),
    (119, 122, "artist-series-seb-mckinnon"),
    (123, 132, "culture-shocks"),
    (133, 137, "prime-slime"),
    (138, 142, "party-hard-shred-harder"),
    (143, 153, "the-walking-dead"),
    (154, 158, "showcase-zendikar-revisited"),
    (159, 163, "read-the-fine-print"),
    (164, 167, "extra-life-2020"),
    # 2021
    (173, 178, "artist-series-mark-poole"),
    (185, 189, "our-show-is-on-friday"),
    (190, 194, "special-guest-fiona-staples"),
    (195, 200, "we-hope-you-like-squirrels"),
    (201, 205, "a-box-of-rocks"),
    (206, 208, "welcome-to-castle-dracula"),
    (209, 213, "phyrexian-praetors-compleat-edition"),
    (214, 219, "valentines-day-2021"),
    (220, 225, "showcase-kaldheim"),
    (226, 230, "fblthp-completely-utterly-totally-lost"),
    (231, 233, "thrilling-tales-of-the-undead"),
    (234, 238, "math-is-for-blockers"),
    (239, 243, "the-unfathomable-crushing-brutality-of-basic-lands"),
    (244, 250, "black-is-magic"),
    (251, 253, "teferis-time-trouble"),
    (254, 258, "the-full-text-lands"),
    (259, 263, "kamigawa-ink"),
    (268, 273, "showcase-strixhaven"),
    (274, 277, "artist-series-thomas-baxa"),
    (278, 281, "artist-series-johannes-voss"),
    (282, 285, "special-guest-jen-bartel"),
    (286, 295, "dan-frazier-is-back"),
    (296, 299, "mothers-day-2021"),
    (300, 304, "mirrodinsanity"),
    (305, 309, "crocodile-jacksons-monstrous-menagerie"),
    (310, 315, "saturday-morning-dnd"),
    (316, 324, "monster-anatomy-101"),
    (325, 334, "pixel-snow-lands"),
    (340, 348, "stranger-things"),
    (349, 363, "showcase-midnight-hunt"),
    (364, 368, "mschf"),
    (369, 372, "purrfection"),
    (373, 378, "extra-life-2021"),
    (379, 383, "heads-i-win-tails-you-lose"),
    (384, 395, "the-astrology-lands"),
    (477, 488, "arcane"),
    # 2022
    (396, 400, "lil-walkers"),
    (401, 405, "lil-giri-saves-the-day"),
    (406, 409, "special-guest-kelogsloops"),
    (410, 414, "introducing-kaito-shizuki"),
    (415, 427, "shades-not-included"),
    (428, 440, "street-fighter"),
    (441, 452, "fortnite"),
    (453, 455, "showcase-streets-of-new-capenna"),
    (456, 476, "artist-series"),
    (489, 500, "artist-series-livia-prima"),
    (1001, 1004, "artist-series-volkan-baga"),
    (1005, 1012, "pride-across-the-multiverse"),
    (1012, 1018, "here-be-dragons"),
    (1020, 1024, "kamigawa-the-manga"),
    (1025, 1040, "warhammer"),
    (1041, 1043, "time-trouble-two"),
    (1044, 1066, "artist-series-victor-adame-minguez"),
    (1067, 1071, "showcase-dominaria-united"),
    (1072, 1074, "dan-fraziers-mox-box"),
    (1075, 1078, "just-some-totally-normal-guys"),
    (1079, 1092, "transformers"),
    (1093, 1096, "artist-series-nils-hamm"),
    (1097, 1117, "the-weirdest-pets"),
    (1122, 1139, "just-add-milk"),
    (1140, 1144, "liller-walkers"),
    (1145, 1150, "extra-life-2022"),
    (1151, 1181, "artist-series-aleksi-briclot"),
    (1182, 1185, "look-at-the-kitties"),
    (1186, 1194, "post-malone"),
    # 2023
    (1155, 1159, "from-cute-to-brute"),
    (1195, 1198, "legendary-flyers"),
    (1199, 1202, "keep-partying-hard"),
    (1203, 1207, "phyrexian-faves"),
    (1208, 1212, "from-cute-to-brute-commanders"),
    (1213, 1236, "showcase-all-will-be-one"),
    (1237, 1242, "dnd-honor-among-thieves"),
    (1243, 1246, "more-borderless-planeswalkers"),
    (1247, 1250, "artist-series-sam-burley"),
    (1251, 1306, "artist-series-rebecca-guay"),
    (1311, 1315, "goblin-and-squabblin"),
    (1316, 1319, "featuring-andrew-maclean"),
    (1325, 1328, "the-fairest-drop-of-all"),
    (1329, 1334, "calling-all-hydra-heads"),
    (1335, 1351, "angels-theyre-just-like-us"),
    (1352, 1357, "evil-dead"),
    (1358, 1367, "featuring-the-mountain-goats"),
    (1368, 1371, "now-on-vhs"),
    (1372, 1381, "doctor-who"),
    (1382, 1386, "featuring-gary-baseman"),
    (1387, 1388, "angels-display-commanders"),
    (1389, 1413, "jurassic-world"),
    (1414, 1418, "buggin-out"),
    (1419, 1423, "lillest-walkers"),
    (1424, 1427, "absolute-annihilation"),
    (1433, 1435, "mycosynthwave"),
    (1444, 1452, "the-princess-bride"),
    (1453, 1457, "magic-the-baseballing"),
    (1458, 1462, "creepshow"),
    (1463, 1467, "gift-wrapped"),
    (1468, 1472, "pixellands-v02"),
    (1473, 1477, "paradise-frost"),
    (1478, 1482, "the-strange-sands"),
    (1483, 1486, "fallout-vault-boy"),
    (1487, 1491, "the-beauty-of-the-beasts"),
    (1492, 1500, "through-the-wormhole"),
    (1501, 1507, "tomb-raider"),
    (1508, 1517, "raining-cats-and-dogs"),
    (1518, 1522, "deceptive-divination"),
    (1523, 1527, "burning-revelations"),
    (1532, 1549, "fallout"),
    (1537, 1540, "ponies-the-galloping-2"),
    (791, 795, "dnd-commander-legends"),
    (1541, 1544, "just-add-milk-second-helpings"),
    (1545, 1549, "prismatic-nightmares"),
    (1557, 1561, "assassins-creed-lethal-legends"),
    (1566, 1569, "showcase-murders-at-karlov-manor"),
    (1570, 1579, "assassins-creed"),
    (1580, 1584, "doctor-who-regeneration"),
    (1585, 1607, "hatsune-miku"),
    (1608, 1613, "featuring-not-a-wolf"),
    (1614, 1626, "outlaw-anthology"),
    (1627, 1646, "featuring-phoebe-wahl"),
    (1647, 1681, "brain-dead"),
    (1682, 1686, "lil-legends"),
    (1687, 1690, "showcase-outlaws-of-thunder-junction"),
    (1691, 1697, "sheldons-spellbook"),
    (1698, 1702, "showcase-bloomburrow"),
    (1703, 1707, "poker-faces"),
    (1708, 1721, "featuring-julie-bell"),
    (1726, 1752, "marvel-superdrop"),
    (1758, 1777, "showcase-duskmourn"),
    (1778, 1806, "dungeons-and-dragons-50th"),
    (1807, 1811, "chucky"),
    (1821, 1824, "pixel-perfect"),
    (1825, 1853, "20-ways-to-win"),
    # Special ranges
    (9990, 9994, "sans-mercy"),
    (9995, 9999, "finally-left-handed-magic-cards"),
]


def get_drop_name_by_collector(collector_number: str) -> str | None:
    """Get drop name based on collector number.

    Args:
        collector_number: Collector number as string (may have letters/symbols)

    Returns:
        Drop name or None if not found

    Note:
        Handles special suffixes like 's' (star), 't' (dagger), 'd' (double-dagger)
    """
    # Extract numeric part (ignore letters and special characters)
    try:
        num = int("".join(c for c in collector_number if c.isdigit()))
    except (ValueError, TypeError):
        return None

    # Find matching range
    for min_col, max_col, drop_name in SLD_COLLECTOR_RANGES:
        if min_col <= num <= max_col:
            return drop_name

    return None


if __name__ == "__main__":
    # Test the mapping
    test_numbers = ["100", "1726", "1731", "1747", "9995"]

    print("SLD Collector Number to Drop Name Mapping")
    print("=" * 70)
    print(f"Total ranges defined: {len(SLD_COLLECTOR_RANGES)}\n")

    print("Test cases:")
    for num in test_numbers:
        drop = get_drop_name_by_collector(num)
        print(f"  {num:>4} -> {drop or 'NOT FOUND'}")
