import hashlib
import json
from pathlib import Path

DATA = json.loads(
    (Path(__file__).parents[1] / "src/epomaker_driver/data/he60-matrices.json").read_text()
)
NAMES = ("defaultMatrix", "defaultFnMatrix", "defaultFnMacMatrix")
DECLARED_NAMES = NAMES + ("defaultFnMACMatrix",)
HASHES = {
    ("2762", "defaultMatrix"): "a5c213ee34e353509ca786d62ad32254b0e444fc97ba0478953905995f00e19d",
    ("2762", "defaultFnMatrix"): "0fc4599696a697483b685d03aae9186216be1d39b16fb6a690e449c221285048",
    (
        "2762",
        "defaultFnMacMatrix",
    ): "899b0752c90a9f8a7bb8472d3b4d084a62a5db155c2f20288c9bebf89cf16757",
    ("2883", "defaultMatrix"): "a5c213ee34e353509ca786d62ad32254b0e444fc97ba0478953905995f00e19d",
    ("2883", "defaultFnMatrix"): "0fc4599696a697483b685d03aae9186216be1d39b16fb6a690e449c221285048",
    (
        "2883",
        "defaultFnMacMatrix",
    ): "899b0752c90a9f8a7bb8472d3b4d084a62a5db155c2f20288c9bebf89cf16757",
    ("3664", "defaultMatrix"): "3795af738c1d86251560547bb6fe40c669297b347a4ee37ffc4cb199bd42368e",
    ("3664", "defaultFnMatrix"): "3d4e727aa93885a81630e071f76b4fb537f10d33d9cda44a2269fe5f1bc6db93",
    (
        "3664",
        "defaultFnMacMatrix",
    ): "bf86efbe985d8a963d99f6847dbaac76b750defd536077ac269563abfca6d2b3",
    ("3662", "defaultMatrix"): "30d1b547a456ff9f9d06d98033b7b6d29a65bf1482873e5f4f26ac9a5757dd99",
    ("3662", "defaultFnMatrix"): "637b38cf9607445d548d8859f0fe969e168e891a2e11e7faa34b28ecfe7c3e47",
    (
        "3662",
        "defaultFnMacMatrix",
    ): "e9f96a2bd42521911c0accbc97c5e4635357a00a9d0ae4619bb2fce4d9c8debe",
    ("3727", "defaultMatrix"): "9eb8b1bea7207b96fdea519efb7a1e7cdd5fed70b4623ed4a79eeca3763c892a",
    ("3727", "defaultFnMatrix"): "8ef17515ac1cad0af713a997982db0f4cfce94edc34a58e2467048ee89be93b4",
    (
        "3727",
        "defaultFnMacMatrix",
    ): "1c4d18ed9c0438800a38314923039b3d51550543e0ecf241f7fb82c21c77c067",
    ("3759", "defaultMatrix"): "9eb8b1bea7207b96fdea519efb7a1e7cdd5fed70b4623ed4a79eeca3763c892a",
    ("3759", "defaultFnMatrix"): "857236b5e0f7f14497e295c819ae42e76d0ae2bf96357f5152cb4876bd5cf34a",
    (
        "3759",
        "defaultFnMacMatrix",
    ): "09cca991f097feb064c89852791b677860951a8132dd3d4e1f0505c5dbcc27c9",
    (
        "3759",
        "defaultFnMACMatrix",
    ): "5ff0bd350d48105cf55127542c47bb442f6bbf80b73479ec656621dacee604b6",
}


def _slots(matrix):
    return {slot for slot in range(128) if any(matrix[slot * 4 : slot * 4 + 4])}


def test_matrix_schema_lengths_and_byte_values():
    assert set(DATA) == {"3662", "3664", "2762", "2883", "3727", "3759"}
    for model in DATA.values():
        assert set(model) == set(NAMES) | (
            {"defaultFnMACMatrix"} if model is DATA["3759"] else set()
        )
        for matrix in model.values():
            assert len(matrix) == 512
            assert all(type(value) is int and 0 <= value <= 255 for value in matrix)


def test_mac_windows_extraction_hashes_are_stable():
    for key, expected in HASHES.items():
        model, name = key
        assert hashlib.sha256(bytes(DATA[model][name])).hexdigest() == expected


def test_declared_uppercase_mac_matrix_is_preserved():
    assert DATA["3759"]["defaultFnMACMatrix"] != DATA["3759"]["defaultFnMacMatrix"]
    assert DATA["3759"]["defaultFnMACMatrix"][0:4] == [0, 0, 0, 0]


def test_normal_matrix_is_shared_but_fn_layouts_are_model_specific():
    assert DATA["3727"]["defaultMatrix"] == DATA["3759"]["defaultMatrix"]
    assert DATA["3727"]["defaultFnMatrix"] != DATA["3759"]["defaultFnMatrix"]
    assert DATA["3727"]["defaultFnMacMatrix"] != DATA["3759"]["defaultFnMacMatrix"]


def test_physical_slots_are_distinct_from_zero_padding():
    normal = _slots(DATA["3727"]["defaultMatrix"])
    assert len(normal) == 61
    assert 1 in normal and 81 in normal
    assert 0 not in normal and 127 not in normal
    assert DATA["3727"]["defaultMatrix"][1 * 4 : 1 * 4 + 4] == [0, 0, 41, 0]
    assert DATA["3759"]["defaultFnMacMatrix"][0:4] == [0, 0, 41, 0]
