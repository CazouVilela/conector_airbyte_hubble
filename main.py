import sys
from airbyte_cdk.entrypoint import launch
from source_hubble import SourceHubble

if __name__ == "__main__":
    source = SourceHubble()
    launch(source, sys.argv[1:])
