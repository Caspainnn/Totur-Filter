import unittest
from src.commute import enrich_prioritized, MapError


class MapPriorityTests(unittest.TestCase):
    def test_ready_recent_orders_first_and_other_uncertainty_skipped(self):
        now=10*86400+36000
        def order(key,stamp,reasons):
            return {'type':1,'status':'needs_confirmation','fields':{'address':key,'schedule':''},'reasons':reasons,'sources':[{'timestamp':stamp}]}
        orders=[order('old',now-86400,['公共交通通勤未核实']),order('uncertain',now,['上课时间待确认','公共交通通勤未核实']),order('today',now-1,['公共交通通勤未核实'])]
        calls=[]
        class Client:
            def commute(self,address,*args):
                calls.append(address);return {'status':'ok','minutes':30}
        result=enrich_prioritized(orders,{'commute':{'maximum_one_way_minutes':60}},Client(),now)
        self.assertEqual(calls,['today','old'])
        self.assertEqual(result[1]['fields']['commute']['reason'],'OTHER_CONDITIONS_PENDING')
        self.assertEqual(orders[1]['fields'],{'address':'uncertain','schedule':''})

    def test_quota_stops_remaining_calls(self):
        calls=[]
        class Client:
            def commute(self,address,*args):
                calls.append(address);raise MapError('DAILY_LIMIT_REACHED')
        orders=[{'type':1,'status':'needs_confirmation','fields':{'address':str(i)},'reasons':['公共交通通勤未核实'],'sources':[{'timestamp':i}]} for i in [1,2,3]]
        result=enrich_prioritized(orders,{'commute':{'maximum_one_way_minutes':60}},Client(),100)
        self.assertEqual(calls,['3'])
        self.assertEqual(result[0]['fields']['commute']['reason'],'MAP_QUOTA_DEFERRED')
