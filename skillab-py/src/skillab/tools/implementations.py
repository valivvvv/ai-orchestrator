"""
Tool implementations — funcțiile efective ale tool-urilor.

Convenție: toate tools primesc params cu `input_dfs` (lista de DataFrames) + parametri specifici.
"""
import pandas

from .registry import register_tool
from .params import JoinDataParams, FilterDataParams


@register_tool
def join_data(params: JoinDataParams) -> pandas.DataFrame:
    """
    Combină două DataFrames pe baza unei chei comune (join).
    Suportă inner, left, right, outer join.

    Args:
        params.input_dfs: [left_dataframe, right_dataframe]
        params.left_key: coloana cheie din primul DataFrame
        params.right_key: coloana cheie din al doilea DataFrame
        params.how: tipul de join

    Returns:
        DataFrame rezultat după join
    """
    left_dataframe = params.input_dfs[0]
    right_dataframe = params.input_dfs[1]
    return pandas.merge(
        left_dataframe,
        right_dataframe,
        left_on=params.left_key,
        right_on=params.right_key,
        how=params.how,
    )


@register_tool
def filter_data(params: FilterDataParams) -> pandas.DataFrame:
    """
    Filtrează un DataFrame pe baza unei condiții.
    Suportă operatori: ==, !=, >, <, >=, <=, contains.

    Args:
        params.input_dfs: [dataframe]
        params.column: coloana pe care se aplică filtrul
        params.operator: operatorul de comparație
        params.value: valoarea pentru comparație

    Returns:
        DataFrame filtrat
    """
    dataframe = params.input_dfs[0]
    column = dataframe[params.column]

    if params.operator == "contains":
        mask = column.astype(str).str.contains(params.value, case=False, na=False)
        return dataframe[mask]

    typed_value = column.dtype.type(params.value)
    if params.operator == "==":
        mask = column == typed_value
    elif params.operator == "!=":
        mask = column != typed_value
    elif params.operator == ">":
        mask = column > typed_value
    elif params.operator == "<":
        mask = column < typed_value
    elif params.operator == ">=":
        mask = column >= typed_value
    else:
        mask = column <= typed_value

    return dataframe[mask]
