from connectors.paper_connector import PaperConnector


def test_paper_connector_get_closed_positions_returns_empty_list():
    connector = PaperConnector()

    result = connector.get_closed_positions()

    assert isinstance(result, list)
    assert result == []