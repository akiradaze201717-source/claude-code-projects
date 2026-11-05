"""balances/accounts.py のユニットテスト。実際の data/accounts.json も検証する。"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from balances.accounts import (
    ACCOUNTS_PATH,
    ASSET,
    LIABILITY,
    Account,
    accounts_by_id,
    load_accounts,
)


class TestLoadAccounts:
    def test_loads_from_custom_path(self, tmp_path):
        path = tmp_path / "accounts.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "a",
                        "name": "口座A",
                        "type": "asset",
                        "category": "銀行",
                        "source": "manual",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        accounts = load_accounts(path)
        assert accounts == [Account("a", "口座A", "asset", "銀行", "manual")]

    def test_accounts_by_id_keyed_correctly(self, tmp_path):
        path = tmp_path / "accounts.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "a",
                        "name": "口座A",
                        "type": "asset",
                        "category": "銀行",
                        "source": "manual",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        by_id = accounts_by_id(path)
        assert by_id["a"].name == "口座A"


class TestRealAccountsFile:
    def test_real_file_loads_without_error(self):
        accounts = load_accounts(ACCOUNTS_PATH)
        assert len(accounts) == 11

    def test_all_ids_unique(self):
        accounts = load_accounts(ACCOUNTS_PATH)
        ids = [a.id for a in accounts]
        assert len(ids) == len(set(ids))

    def test_all_types_valid(self):
        accounts = load_accounts(ACCOUNTS_PATH)
        assert all(a.type in (ASSET, LIABILITY) for a in accounts)

    def test_expected_accounts_present(self):
        by_id = accounts_by_id(ACCOUNTS_PATH)
        for expected_id in [
            "gmo_coin_jpy",
            "gmo_coin_crypto",
            "sbi_sec_domestic",
            "sbi_sec_fund",
            "sbi_sec_us",
            "docomo_sbi_bank",
            "paypay",
            "resona_bank",
            "smbc_card",
            "saison_gold",
            "jcb_card",
        ]:
            assert expected_id in by_id
