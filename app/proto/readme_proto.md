
# How to generate Protobuf interface for Python.
We are going to use Betterproto library because it is modern and cool.
https://github.com/danielgtaylor/python-betterproto

## [Optional] Create a virtual environment
`python -m venv venv && source venv/bin/activate`

## Install both the library and compiler
`pip install "betterproto[compiler]"`

## Install just the library (to use the generated code output)
`pip install betterproto`

## Install other dependencies
`python -m pip install grpcio grpcio-tools`


Download Cosmos SDK (AFAIK THORChain uses v0.45.1, check it):
```
git clone https://github.com/cosmos/cosmos-sdk.git
cd cosmos-sdk
git checkout v0.45.1
cd ..
```


Download MayaNode source code (https://gitlab.com/mayachain/mayanode) and switch your working directory:
```
git clone https://gitlab.com/mayachain/mayanode.git
cd mayanode
git checkout v1.107.1
```


Command to generate Python files:
```mkdir -p pylib
python -m pip install grpcio
python -m pip install grpcio-tools
python -m grpc_tools.protoc -I "proto" -I "third_party/proto" -I "../cosmos-sdk/proto" --python_betterproto_out=pylib proto/mayachain/v1/x/mayachain/types/*.proto "../cosmos-sdk/proto/cosmos/tx/v1beta1/tx.proto"
```

Now move the contents of "pylib" here.

### Troubleshooting:
If you have errors concerning "safe_unicode" imports, just downgrade your library:
`pip install markupsafe==2.0.1`
