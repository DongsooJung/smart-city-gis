from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib.util,xml.etree.ElementTree as ET,json
import pytest

spec=importlib.util.spec_from_file_location('collector',Path(__file__).resolve().parents[1]/'scripts/fetch_osm_data.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def xml(body):return ET.fromstring('<osm>'+body+'</osm>')
N1='<node id="1" lon="127.04" lat="37.49"><tag k="amenity" v="cafe"/></node>'
N2='<node id="2" lon="127.04" lat="37.49"><tag k="amenity" v="cafe"/></node>'

def test_colocated_distinct_nodes_survive_but_duplicate_responses_and_outside_points_do_not():
    p=xml(N1+N2+'<node id="3" lon="128" lat="37.49"><tag k="amenity" v="cafe"/></node>')
    result=m.pois([p,p]);assert [f['properties']['osm_id'] for f in result['features']]==['1','2']

def test_conflicting_nodes_are_not_silently_reconciled():
    with pytest.raises(ValueError,match='Conflicting'):m.pois([xml(N1),xml(N1.replace('127.04','127.05'))])

def test_border_ways_and_reverse_edges_are_deduplicated_without_changing_lengths():
    p=xml('<node id="1" lon="127.04" lat="37.49"/><node id="2" lon="127.041" lat="37.49"/><way id="7"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way>')
    result=m.graph([p,p]);assert len(result['nodes'])==2;assert len(result['edges'])==1;assert 80<result['edges'][0][2]<100
    with pytest.raises(ValueError,match='Incomplete'):m.graph([xml('<node id="1" lon="127.04" lat="37.49"/><way id="7"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way>')])

def test_failed_partial_collection_leaves_previous_published_inputs_untouched():
    with TemporaryDirectory() as tmp:
        folder=Path(tmp);old=folder/'metadata.json';old.write_text(json.dumps({'fetchedAt':'2026-08-27'}));before=old.read_bytes()
        with patch.object(m,'OUT',folder),patch.object(m,'request_map',side_effect=[(xml(N1),{}),RuntimeError('source failed')]),patch('sys.argv',['fetch_osm_data.py','--raw-dir',str(folder/'raw')]):
            with pytest.raises(RuntimeError,match='source failed'):m.main()
        assert old.read_bytes()==before;assert not (folder/'gangnam_pois.geojson').exists()
