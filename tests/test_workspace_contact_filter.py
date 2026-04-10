import unittest

from workspace_contact_filter import workspace_sender_allowed


class WorkspaceContactFilterTests(unittest.TestCase):
    def test_all_mode_allows_any_sender(self):
        self.assertTrue(
            workspace_sender_allowed(
                mode="all",
                sender_ids={"125370296725569@lid"},
                allowed_ids=set(),
            )
        )

    def test_only_mode_requires_match(self):
        self.assertTrue(
            workspace_sender_allowed(
                mode="only",
                sender_ids={"125370296725569@lid"},
                allowed_ids={"125370296725569@lid"},
            )
        )
        self.assertFalse(
            workspace_sender_allowed(
                mode="only",
                sender_ids={"917307134641@s.whatsapp.net"},
                allowed_ids={"125370296725569@lid"},
            )
        )

    def test_except_mode_blocks_matching_sender(self):
        self.assertFalse(
            workspace_sender_allowed(
                mode="except",
                sender_ids={"125370296725569@lid"},
                allowed_ids={"125370296725569@lid"},
            )
        )
        self.assertTrue(
            workspace_sender_allowed(
                mode="except",
                sender_ids={"917307134641@s.whatsapp.net"},
                allowed_ids={"125370296725569@lid"},
            )
        )

    def test_invalid_mode_falls_back_to_all(self):
        self.assertTrue(
            workspace_sender_allowed(
                mode="invalid",
                sender_ids={"917307134641@s.whatsapp.net"},
                allowed_ids={"125370296725569@lid"},
            )
        )


if __name__ == "__main__":
    unittest.main()
