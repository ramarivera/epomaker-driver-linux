import hashlib
import json
from pathlib import Path

DATA = json.loads(
    (Path(__file__).parents[1] / "src/epomaker_driver/data/he60-matrices.json").read_text()
)
NAMES = ("defaultMatrix", "defaultFnMatrix", "defaultFnMacMatrix")
DECLARED_NAMES = NAMES + ("defaultFnMACMatrix",)
HASHES = {
    ("3692", "defaultMatrix"): "2344387f62b34cc036750937fff4cd3ee93b0cb74dd50db4e74f95cb815d8c0b",
    ("3692", "defaultFnMatrix"): "939b37d9dceb483c54c52671da2385e71482f41ef5f7dba9196387fc052c9abb",
    (
        "3692",
        "defaultFnMacMatrix",
    ): "30a4550d7c963ce4e2d043ea2b49bfaac4e5e2571b73b89d9e8b2932a599b597",
    ("3703", "defaultMatrix"): "533533fc829ca9c491b513571ea1a1351286af6f29f008f7bfd95ba08aa73d8b",
    ("3703", "defaultFnMatrix"): "45c053d91d06a2c8db07807a63c8dcf676cbafdb1f5feb35e022b3c10038718d",
    (
        "3703",
        "defaultFnMacMatrix",
    ): "ad776ce7a5de3a0ffa83688f93887734049e2c72e59ca154c4ef2876b21a6e7c",
    ("2761", "defaultMatrix"): "a5c213ee34e353509ca786d62ad32254b0e444fc97ba0478953905995f00e19d",
    ("2761", "defaultFnMatrix"): "6ac7d302a1b062e25db6de1bb88cef4fde3d160b13e03c2947551c2d4d97a1be",
    (
        "2761",
        "defaultFnMacMatrix",
    ): "09cca991f097feb064c89852791b677860951a8132dd3d4e1f0505c5dbcc27c9",
    ("2959", "defaultMatrix"): "7d6c7647e687b54ec58ac3b8b748c30f31dda2c40279d88d05170a8dbdaa2164",
    ("2959", "defaultFnMatrix"): "cce865b2ab889319bc3d9dd2a235e040d8458cb9596b9aa02f41773b7cac7c6f",
    (
        "2959",
        "defaultFnMacMatrix",
    ): "a13ac1a8236c1df26ac5380b308eec8ce27c81b09fd749311ff5293daa72fbcc",
    ("2465", "defaultMatrix"): "927321320e81f3e78714030fffe2e5dbea90b520e0eceb8e77948cf64560f0c1",
    ("2465", "defaultFnMatrix"): "4088d7fe10950a6e812be52a7e1ac857cf6e999f1bbb74024ba0fd2f59f80cf1",
    (
        "2465",
        "defaultFnMacMatrix",
    ): "4088d7fe10950a6e812be52a7e1ac857cf6e999f1bbb74024ba0fd2f59f80cf1",
    ("2586", "defaultMatrix"): "8d741fd99f8523838645aafc0f7f4a30950a7f2cec322defc49855c3ac7e9a32",
    ("2586", "defaultFnMatrix"): "5850ef307f7981697fce4429508e5823e92e6611a25bcf64c6898b4ac060376a",
    (
        "2586",
        "defaultFnMacMatrix",
    ): "09cca991f097feb064c89852791b677860951a8132dd3d4e1f0505c5dbcc27c9",
    ("2870", "defaultMatrix"): "4ccae2e374ff5646ffb9afd404a6c4bd39e2f9c5dc3d2d8c3316959da92a56b5",
    ("2870", "defaultFnMatrix"): "858d79c1ad51b7e267617a48740a5675008553f01c9b87f95f349b9f00f1953e",
    (
        "2870",
        "defaultFnMacMatrix",
    ): "03133080055178aa8a70bd00174235631a5dd7b758b7f0dbc9d77551fef5fd0d",
    ("3691", "defaultMatrix"): "2344387f62b34cc036750937fff4cd3ee93b0cb74dd50db4e74f95cb815d8c0b",
    ("3691", "defaultFnMatrix"): "cb0466d547051f86f71997521b4e65b8324886d26b8a8e7c798ab43499dabaa4",
    (
        "3691",
        "defaultFnMacMatrix",
    ): "4e506e52e05b4b8e45437b1a4b0ba5883bd0502188143599f35c4532be83f349",
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
    ("3746", "defaultMatrix"): "c864e07a8521a009235d8b4632a8cf0f3d3cfd0fa64cee7485cf38b166682aff",
    ("3746", "defaultFnMatrix"): "e7013592b988cbd0b2687bd8716fde7fa3d4fd545dce08209ed4381add3c3a21",
    (
        "3746",
        "defaultFnMacMatrix",
    ): "6929e22667a23a22092f0e201cd862b8464926d6c89d5f85a114be1c2ec2ee23",
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
    assert set(DATA) == {
        "3662",
        "3664",
        "3746",
        "3365",
        "2762",
        "2883",
        "3727",
        "3759",
        "2465",
        "2586",
        "2870",
        "3691",
        "3692",
        "3703",
        "2761",
        "2959",
    }
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
