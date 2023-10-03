#  Copyright (c) 2019-2023 SRI International.

from prism.common.crypto.halfkey.diffiehellman import DiffieHellman

FIXED_PARAMS = \
    {0: 0,
     1: int('313813187790542690281665637110422325340981137054'
            '184443047830656360087203323474681302408579209677'
            '049941083948290095764735163827618798747238185205'
            '524138568414529632162556503372753133839716112213'
            '390304121773544518051885066736513555278391028089'
            '577468054825075573135121168620565205518734163839'
            '355149377221238973897322607689481942522221430259'
            '175658456365434057325117900983020473946960620092'
            '326899231159649151212236545588507872772980302252'
            '220630601597820365433745247345445832076823281105'
            '145517685134701139664322504709843104411682668981'
            '596789736373873495070244723122427682712001599017'
            '11728619625315700609679549206292050068827'),
     2: 2, 3: None}


# # use this test to generate a file with 3072-bit DH parameters as a dictionary
# @unittest.skip("takes 1-10 minutes so skipping normally")
# def test_params(self):
#     path = "DH3072.dhp"
#     params1 = DiffieHellman.generate_parameters(3072)
#     dict1 = DiffieHellman.parameters_to_dict(params1)
#     with open(path, 'wb') as f:
#         pickle.dump(dict1, f)
#     with open(path, 'rb') as f:
#         dict2 = pickle.load(f)
#     assert dict1 == dict2, 'dicts stored and retrieved are equal'

def test_key_exchange():
    # simulate key exchange between two machines,
    # communicating by generating public dictionaries
    # hardcode a set of parameters for speedier tests
    system = DiffieHellman.load_system(FIXED_PARAMS)

    m1_privk1 = system.generate_private()
    m1_pubk1 = m1_privk1.public_key()
    pubd1 = m1_pubk1.cbor()

    # pubd1 is published, now we're on the other machine
    m2_pubk1 = system.load_public(pubd1)
    m2_privk2 = m2_pubk1.generate_private()
    m2_pubk2 = m2_privk2.public_key()
    pubd2 = m2_pubk2.cbor()

    # back to first machine
    m1_pubk2 = system.load_public(pubd2)
    m1_shared_key = m1_privk1.exchange(m1_pubk2)

    # second machine
    m2_shared_key = m2_privk2.exchange(m2_pubk1)

    assert m1_shared_key == m2_shared_key, \
        "Machines 1 and 2 generate same shared key."

    # Test serialization
    data = m1_privk1.serialize()
    m1_pk1b = system.load_private(data)

    m1_shared_key_b = m1_pk1b.exchange(m1_pubk2)
    assert m1_shared_key == m1_shared_key_b, \
        "Machine 1 generates same shared key after " \
        "serialization"
