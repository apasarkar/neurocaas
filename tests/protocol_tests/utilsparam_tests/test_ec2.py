import pytest
import localstack_client.session
import logging
import os
import ncap_iac.protocols.utilsparam.ec2 as ec2
import ncap_iac.protocols.utilsparam.env_vars
from ncap_iac.protocols.utilsparam.pricing import get_price, get_region_name, region_id

session = localstack_client.session.Session()

ec2_client = session.client("ec2")
ec2_resource = session.resource("ec2")

@pytest.fixture
def kill_instances():
    """Kill if unattended instances have been left running."""
    yield "kill uncleaned instances"
    session = localstack_client.session.Session()
    ec2_resource = session.resource("ec2")
    instances = ec2_resource.instances.filter(Filters = [{"Name":"instance-state-name","Values":["running"]}]) 
    for instance in instances:
        instance.terminate()

@pytest.fixture
def patch_boto3_ec2(monkeypatch):
    ec2_client = session.client("ec2")
    ec2_resource = session.resource("ec2")
    monkeypatch.setattr(ec2,"ec2_resource",session.resource("ec2"))
    monkeypatch.setattr(ec2,"ec2_client",session.client("ec2"))
    yield "patching resources."

@pytest.fixture
def create_ami():
    instance = ec2_resource.create_instances(MaxCount = 1,MinCount=1)[0]
    ami = ec2_client.create_image(InstanceId=instance.instance_id,Name = "dummy")
    yield ami["ImageId"]

@pytest.fixture
def create_ami_2():
    """Just bc we want two different ones. 

    """
    instance = ec2_resource.create_instances(MaxCount = 1,MinCount=1)[0]
    ami = ec2_client.create_image(InstanceId=instance.instance_id,Name = "dummy2")
    yield ami["ImageId"]

@pytest.fixture
def loggerfactory():
    class logger():
        def __init__(self):
            self.logs = []
        def append(self,message):    
            self.logs.append(message)
        def write(self): 
            logging.warning("SEE Below: \n"+str("\n".join(self.logs)))
    yield logger()        


def test_launch_new_instances(patch_boto3_ec2,loggerfactory,create_ami,kill_instances):
    instance_type = "t2.micro"
    ami = create_ami 
    logger = loggerfactory 
    number = 1
    add_size = 200
    duration = None
    message = patch_boto3_ec2

    response = ec2.launch_new_instances(instance_type,ami,logger,number,add_size,duration)
    info = ec2_client.describe_instances(InstanceIds=[response[0].id])

    assert len(info["Reservations"][0]["Instances"]) == 1
    info_instance = info["Reservations"][0]["Instances"][0]
    
    assert info_instance["ImageId"] == ami
    assert info_instance["InstanceType"] == instance_type
    
def test_launch_new_instances_spot(patch_boto3_ec2,loggerfactory,create_ami,kill_instances):
    """This doesn't actually check if the instance is spot, just that the code works.   
    """
    instance_type = "t2.micro"
    ami = create_ami 
    logger = loggerfactory 
    number = 1
    add_size = 200
    duration = 20
    message = patch_boto3_ec2

    response = ec2.launch_new_instances(instance_type,ami,logger,number,add_size,duration)
    info = ec2_client.describe_instances(InstanceIds=[response[0].id])

    assert len(info["Reservations"][0]["Instances"]) == 1
    info_instance = info["Reservations"][0]["Instances"][0]
    
    assert info_instance["ImageId"] == ami
    assert info_instance["InstanceType"] == instance_type

@pytest.mark.parametrize("duration,value",([10,"10"],[None,"20"]))
def test_launch_new_instances_with_tags(patch_boto3_ec2,loggerfactory,create_ami,duration,value,kill_instances):
    instance_type = "t2.micro"
    ami = create_ami 
    logger = loggerfactory 
    number = 1
    add_size = 200
    message = patch_boto3_ec2

    response = ec2.launch_new_instances_with_tags(instance_type,ami,logger,number,add_size,duration)
    info = ec2_client.describe_instances(InstanceIds=[response[0].id])

    assert len(info["Reservations"][0]["Instances"]) == 1
    info_instance = info["Reservations"][0]["Instances"][0]
    
    assert info_instance["ImageId"] == ami
    assert info_instance["InstanceType"] == instance_type
    assert info_instance["Tags"] == [
            {"Key":"PriceTracking","Value":"On"},
            {"Key":"Timeout","Value":value} ## check for the exact keys and values. This is a filter on the kinds of stack updates we allow.
            ]
    
@pytest.mark.parametrize("duration,value,group,analysis,job",([10,"10",None,None,None],[None,"20",None,None,None],[None,"20","usergroup",None,None],[None,"20","usergroup","analysis1",None],[None,"20","usergroup","analysis1","job15__analysis1"],[None,"20",None,"analysis1","job15__analysis1"],[None,"20",None,"analysis1",None],[None,"20",None,None,"job15__analysis1"]))
def test_launch_new_instances_with_tags_additional(patch_boto3_ec2,loggerfactory,create_ami,duration,value,group,analysis,job,kill_instances):
    instance_type = "t2.micro"
    ami = create_ami 
    logger = loggerfactory 
    number = 1
    add_size = 200
    message = patch_boto3_ec2

    response = ec2.launch_new_instances_with_tags_additional(instance_type,ami,logger,number,add_size,duration,group,analysis,job)
    info = ec2_client.describe_instances(InstanceIds=[response[0].id])

    assert len(info["Reservations"][0]["Instances"]) == 1
    info_instance = info["Reservations"][0]["Instances"][0]
    
    tags = [
        {"Key":"PriceTracking","Value":"On"},
        {"Key":"Timeout","Value":value} ## check for the exact keys and values. This is a filter on the kinds of stack updates we allow.
    ]
    
    additional_tags = {"group":group,"analysis":analysis,"job":job}
    for at in additional_tags.items():
        if at[1] is not None:
            tags.append({"Key":at[0],"Value":at[1]})
    
    assert info_instance["ImageId"] == ami
    assert info_instance["InstanceType"] == instance_type
    assert info_instance["Tags"] == tags; "Tags are not formatted correctly!"   


def test_get_active_instances(patch_boto3_ec2,monkeypatch,loggerfactory,create_ami,create_ami_2,kill_instances):    
    instance_type = "t2.micro"
    ami = create_ami 
    ami2 = create_ami_2
    logger = loggerfactory 
    number = 5
    add_size = 200
    duration = 5
    group = "usergroup" 
    analysis = "ana1"
    job = "job1"

    message = patch_boto3_ec2
    response1 = ec2.launch_new_instances_with_tags_additional(instance_type,ami,logger,number,add_size,duration,group,analysis,job)
    response2 = ec2.launch_new_instances_with_tags_additional(instance_type,ami2,logger,1,add_size,duration,group,analysis,job)
    assert len([i for i in ec2.get_active_instances_ami(ami)]) == 5
    assert ec2.duration_active_instances_ami(ami) == 5*5
    assert len([i for i in ec2.get_active_instances_ami(ami2)]) == 1
    response1 = ec2.launch_new_instances_with_tags_additional("p2.xlarge",ami,logger,number,add_size,duration,group,analysis,job)
    assert len([i for i in ec2.get_active_instances_ami(ami)]) == 10 









