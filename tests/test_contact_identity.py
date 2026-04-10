import unittest

from contact_identity import (
    choose_preferred_contact_id,
    extract_sender_id_candidates,
    normalize_contact_chat_id,
)


class ContactIdentityTests(unittest.TestCase):
    def test_normalize_contact_chat_id_from_phone_digits(self):
        self.assertEqual(
            normalize_contact_chat_id("+91 73071 34641"),
            "917307134641@s.whatsapp.net",
        )

    def test_normalize_contact_chat_id_keeps_jid_and_lowercases(self):
        self.assertEqual(
            normalize_contact_chat_id("125370296725569@LID"),
            "125370296725569@lid",
        )

    def test_choose_preferred_contact_id_prefers_lid(self):
        selected = choose_preferred_contact_id(
            [
                "917307134641@s.whatsapp.net",
                "917307134641@c.us",
                "125370296725569@lid",
            ]
        )
        self.assertEqual(selected, "125370296725569@lid")

    def test_extract_sender_id_candidates_skips_groups(self):
        payload = {
            "participant": "125370296725569@lid",
            "author": "917307134641@s.whatsapp.net",
            "from": "120363197683574605@g.us",
            "_data": {
                "key": {
                    "participant": "917307134641@c.us",
                    "participantAlt": "917307134641@s.whatsapp.net",
                }
            },
        }
        chat_id = "120363197683574605@g.us"
        candidates = extract_sender_id_candidates(payload, chat_id)
        self.assertIn("125370296725569@lid", candidates)
        self.assertIn("917307134641@s.whatsapp.net", candidates)
        self.assertIn("917307134641@c.us", candidates)
        self.assertTrue(all(not jid.endswith("@g.us") for jid in candidates))

    def test_choose_preferred_contact_id_ignores_group_ids(self):
        selected = choose_preferred_contact_id(
            [
                "120363197683574605@g.us",
                "917307134641@c.us",
                "125370296725569@lid",
            ]
        )
        self.assertEqual(selected, "125370296725569@lid")


if __name__ == "__main__":
    unittest.main()
