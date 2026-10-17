import hashlib
import sqlite3
import unittest
import tempfile
from pathlib import Path
from src.wechat_source import IncompleteReadError, resolve_groups, query_group, require_allowed


def database(group='one@chatroom', broken=False):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE contact(username TEXT,nick_name TEXT)')
    c.execute('INSERT INTO contact VALUES (?,?)', (group, '测试群'))
    table = 'Msg_' + hashlib.md5(group.encode()).hexdigest()
    if broken:
        c.execute(f'CREATE TABLE {table}(create_time INTEGER)')
    else:
        c.execute(f'CREATE TABLE {table}(local_id INTEGER, server_id INTEGER, local_type INTEGER, create_time INTEGER, message_content TEXT, compress_content BLOB)')
        c.executemany(f'INSERT INTO {table} VALUES (?,?,1,?,?,NULL)', [(1, 101, 100, '测试订单A'), (2, 102, 100, '测试订单B'), (3, 103, 99, '旧消息')])
    return c


class SourceTests(unittest.TestCase):
    def test_whitelist_rejects_private_and_unknown(self):
        for candidate in ('filehelper', 'other@chatroom', None):
            with self.assertRaises(PermissionError):
                require_allowed(candidate, {'one@chatroom'})

    def test_exact_match_and_duplicate_names_stop(self):
        with database() as c:
            self.assertEqual(resolve_groups(c, ['测试群']), {'one@chatroom': '测试群'})
            c.execute('INSERT INTO contact VALUES (?,?)', ('two@chatroom', '测试群'))
            with self.assertRaises(IncompleteReadError):
                resolve_groups(c, ['测试群'])

    def test_missing_group_stops(self):
        with database() as c:
            with self.assertRaises(IncompleteReadError):
                resolve_groups(c, ['不存在'])

    def test_same_second_across_shards_not_lost(self):
        with database() as a, database() as b:
            messages = query_group([('a', a), ('b', b)], 'one@chatroom', '测试群', 100, 100)
            self.assertEqual(len(messages), 4)
            self.assertEqual({m['timestamp'] for m in messages}, {100})
            self.assertEqual(len({m['id'] for m in messages}), 2)

    def test_bad_schema_is_failure_not_empty(self):
        with database(broken=True) as c:
            with self.assertRaises(IncompleteReadError):
                query_group([('a', c)], 'one@chatroom', '测试群', 0, 200)

    def test_limit_does_not_silently_truncate(self):
        with database() as c:
            with self.assertRaises(IncompleteReadError):
                query_group([('a', c)], 'one@chatroom', '测试群', 0, 200, limit=2)

    def test_absent_table_is_no_local_history(self):
        with database() as c:
            self.assertEqual(query_group([('a', c)], 'missing@chatroom', '测试群', 0, 200), [])

    def test_invalid_whitelist_fails(self):
        with database() as c:
            for names in ([], ['测试群', '测试群'], ['']):
                with self.assertRaises(IncompleteReadError):
                    resolve_groups(c, names)

    def test_expected_account_cannot_change(self):
        from src.wechat_source import verify_source_identity
        with self.assertRaises(IncompleteReadError):
            verify_source_identity('accountA', 'accountB', {'shard0'}, {'shard0'})
        with self.assertRaises(IncompleteReadError):
            verify_source_identity('accountA', 'accountA', {'shard0'}, {'shard0', 'shard1'})

    def test_invalid_current_wal_frame_never_counts_as_applied(self):
        from src.wechat_source import merge_wal_strict
        import struct
        with tempfile.TemporaryDirectory() as folder:
            dst, wal = Path(folder) / 'copy.db', Path(folder) / 'source-wal'
            dst.write_bytes(b'\0' * 4096)
            header = struct.pack('>IIII', 0x377F0682, 3007000, 4096, 0) + b'salt1234' + b'\0' * 8
            frame = struct.pack('>II', 1, 1) + b'salt1234' + b'\0' * 8 + b'\0' * 4096
            wal.write_bytes(header + frame)
            with self.assertRaisesRegex(IncompleteReadError, 'WAL_FRAME_AUTH_FAILED'):
                merge_wal_strict(dst, wal, b'K' * 32, b'S' * 16, lambda key, page, pg: page)

    def test_authenticated_committed_wal_page_not_skipped_by_byte_heuristic(self):
        from src.wechat_source import merge_wal_strict
        import struct
        import hmac
        with tempfile.TemporaryDirectory() as folder:
            dst, wal = Path(folder) / 'copy.db', Path(folder) / 'source-wal'
            dst.write_bytes(b'\0' * 4096)
            mac = hashlib.pbkdf2_hmac('sha512', b'K' * 32, bytes(v ^ 0x3A for v in b'S' * 16), 2, dklen=32)
            payload = b'Q' * 4032
            digest = hmac.new(mac, payload[16:] + struct.pack('<I', 1), hashlib.sha512).digest()
            header = struct.pack('>IIII', 0x377F0682, 3007000, 4096, 0) + b'salt1234' + b'\0' * 8
            frame = struct.pack('>II', 1, 1) + b'salt1234' + b'\0' * 8 + payload + digest
            wal.write_bytes(header + frame)
            applied = merge_wal_strict(dst, wal, b'K' * 32, b'S' * 16, lambda key, page, pg: b'Z' * 4096)
            self.assertEqual(applied, 1)
            self.assertEqual(dst.read_bytes()[:16], b'Z' * 16)

    def test_old_generation_tail_is_not_an_uncommitted_transaction(self):
        from src.wechat_source import merge_wal_strict
        import struct
        with tempfile.TemporaryDirectory() as folder:
            dst, wal = Path(folder) / 'copy.db', Path(folder) / 'source-wal'
            dst.write_bytes(b'\0' * 4096)
            header = struct.pack('>IIII', 0x377F0682, 3007000, 4096, 0) + b'newsalt0' + b'\0' * 8
            frame = struct.pack('>II', 1, 1) + b'oldsalt0' + b'\0' * 8 + b'\0' * 4096
            wal.write_bytes(header + frame)
            self.assertEqual(merge_wal_strict(dst, wal, b'K' * 32, b'S' * 16, lambda *args: (_ for _ in ()).throw(AssertionError())), 0)


if __name__ == '__main__':
    unittest.main()
