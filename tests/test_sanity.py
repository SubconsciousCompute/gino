def tcmoest_imports():
    import cmo
    print(dir(cmo))

    import cmo.metric


    print(dir(cmo.metric))
    assert "available_metrics" in dir(cmo.metric)


def test_foo():
    print("nothing here")
    assert True
