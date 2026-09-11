from gitops_layer import CodeValidator
def test_protected_secrets(): assert CodeValidator.is_protected_path('.streamlit/secrets.toml')
def test_parent_path_rejected():
    import pytest
    with pytest.raises(ValueError): CodeValidator.normalize_path('../main.py')
