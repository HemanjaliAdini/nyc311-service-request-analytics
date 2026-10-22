import io
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock
from extract_cohort import get_json

class ApiFailureTests(unittest.TestCase):
    def test_rate_limit_retry(self):
        opener=Mock(side_effect=[HTTPError('https://example.test',429,'limit',{'Retry-After':'2'},None),io.BytesIO(b'[{"id":1}]')])
        sleeper=Mock()
        data,raw,_=get_json({},opener=opener,sleeper=sleeper)
        self.assertEqual(data,[{'id':1}])
        self.assertEqual(raw,b'[{"id":1}]')
        sleeper.assert_called_once_with(2)

    def test_bad_query_no_retry(self):
        opener=Mock(side_effect=HTTPError('https://example.test',400,'bad query',{},None))
        sleeper=Mock()
        with self.assertRaises(HTTPError): get_json({},opener=opener,sleeper=sleeper)
        self.assertEqual(opener.call_count,1)
        sleeper.assert_not_called()

    def test_server_failure_bounded(self):
        opener=Mock(side_effect=HTTPError('https://example.test',503,'unavailable',{},None))
        sleeper=Mock()
        with self.assertRaises(HTTPError): get_json({},opener=opener,sleeper=sleeper)
        self.assertEqual(opener.call_count,4)
        self.assertEqual([c.args[0] for c in sleeper.call_args_list],[1,2,4])

if __name__=='__main__': unittest.main()
