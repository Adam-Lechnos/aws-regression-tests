import boto3
import json
import time
import sys
import re

asgName=sys.argv[1]
region=sys.argv[2]
client = boto3.client('autoscaling', region_name=region)
clientEC2 = boto3.client('ec2', region_name=region)
clientCheck = boto3.client('autoscaling', region_name=region)

print ("\n=================================")
print ("====Starting regression tests====")
print ("=================================\n")

time.sleep(5)

instanceRefreshCheck = client.describe_instance_refreshes(
    AutoScalingGroupName=asgName,
)

if not instanceRefreshCheck['InstanceRefreshes']:
    print("====No Instance Refresh tasks listed====\n")
else:
   print("Waiting for Instance Refresh to be marked successful..")
   while instanceRefreshCheck['InstanceRefreshes'][0]['Status'] != "Successful":
     time.sleep(60*1)
     instanceRefreshCheck = client.describe_instance_refreshes(
     AutoScalingGroupName=asgName,
     )
   print("====Instance Refresh marked successful====\n")
   print(instanceRefreshCheck['InstanceRefreshes'][0]['Status'])


responseDescribeASG = client.describe_auto_scaling_groups(
    AutoScalingGroupNames=[
        asgName,
    ],
)

instanceTest=responseDescribeASG['AutoScalingGroups'][0]['Instances']

instanceList = []

for item in instanceTest:
    for k,v in item.items():
        if k == 'InstanceId':
            instaceList = instanceList.append(v)

responseEC2ops = clientEC2.describe_instance_status(
    InstanceIds=instanceList,
    IncludeAllInstances=True
)

InstanceCheck=responseEC2ops['InstanceStatuses']

runningList = []

for item in InstanceCheck:
    for k,v in item.items():
        if k == 'InstanceState':
            for k2,v2 in v.items():
                if k2 == 'Name':
                    runningList.append(v2)

runningTest = [x for x in runningList if 'running' != x]
if len(runningTest) > 0:
    sys.exit("====Not all ASG instances are in a running state, aborting====")
else:
    print("====ASG instances are in a running state====\n")

del responseDescribeASG

responseDescribeASG = client.describe_auto_scaling_groups(
    AutoScalingGroupNames=[
        asgName,
    ],
)

getASGdesired=responseDescribeASG['AutoScalingGroups'][0]['DesiredCapacity']
getASGhealthyec2s=responseDescribeASG['AutoScalingGroups'][0]['Instances']

ASGhealthyList = []

for item in getASGhealthyec2s:
    for k, v in item.items():
        if k == 'HealthStatus':
            ASGHealthyList = ASGhealthyList.append(v)

if len(ASGhealthyList) == getASGdesired:
    print(f"====ASG instances marked healthy and match the desired capacity====\n")
else:
    sys.exit(f"====Not all ASG instances marked healthy accoding to the desired capacity, aborting====")

suspendedProcessesOut=responseDescribeASG['AutoScalingGroups'][0]['SuspendedProcesses']

spList = ""

for item in suspendedProcessesOut:  
    for k, v in item.items():
        if k == 'ProcessName':
            spList += v +', '
            

spList = spList[:-2] 
print(f"====Suspended processes check====")

if len(suspendedProcessesOut) > 0:
    print(f"Caution, suspended processses present\n  {spList}")
else:
    print(f"Not defined")

instanceStatus=responseDescribeASG['AutoScalingGroups'][0]['Instances'][0]['LifecycleState']

instance = ""
instanceHealth = ""
instanceStatus = ""
print(f"\n====ASG Instance Service Status Checks====\nWating for ASG healthchecks to mark all instances InService..")
timeout = time.time() + 60*3
while instanceStatus != 'InService':
    time.sleep(2)
    responseDescribeASG = client.describe_auto_scaling_groups(
    AutoScalingGroupNames=[
        asgName,
    ],
    )
    instance=responseDescribeASG['AutoScalingGroups'][0]['Instances'][0]['InstanceId']
    instanceHealth=responseDescribeASG['AutoScalingGroups'][0]['Instances'][0]['HealthStatus']
    instanceStatus=responseDescribeASG['AutoScalingGroups'][0]['Instances'][0]['LifecycleState']
    print(f"ASG Service State: {instanceStatus}")
    del responseDescribeASG
    if time.time() > timeout:
        sys.exit("Failed to bring instance into InService state, aborting")
    print('Ensuring instance is ready for SSM commands..')
    time.sleep(20)

print(f"\n====ASG status check=====\nInstance Id: {instance}")
print(f"Instance Health: {instanceHealth}")
print(f"ASG Service State: {instanceStatus}")

ssm_client = boto3.client('ssm', region_name=region)
response = ssm_client.send_command(
    InstanceIds=[instance],
    DocumentName="AWS-RunShellScript",
    Parameters={"commands": ["hostname", "uptime"]}
)
command_id = response['Command']['CommandId']
time.sleep(5)
SSMcommandOut = ssm_client.get_command_invocation(
      CommandId=command_id,
      InstanceId=instance
    )

SSMcommandOutStatus = SSMcommandOut['ResponseMetadata']['HTTPStatusCode']

print(f"\n====Application testing commands=====")
if SSMcommandOutStatus == 200:
    print(f"SSM command invocation completed. Status {SSMcommandOutStatus}\nWaiting for command executions to complete..")
  
    timeout = time.time() + 60*3
    while SSMcommandOut['Status'] != "Success":
        time.sleep(2)
        SSMcommandOut = ssm_client.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance
        )
        if time.time() > timeout:
            sys.exit(f"\nSSM commands failed to complete, aborting")
        elif SSMcommandOut['Status'] == "Failed":
            sys.exit(f"\nCommand failed:\n{SSMcommandOut['StandardErrorContent']}")

else:
    sys.exit(f"SSM command executionn failed, aborting. Status {SSMcommandOutStatus}")

SSMcommandOut = ssm_client.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance
        )

SSMcommandOutStatus = SSMcommandOut['Status']
SSMcommandOutStatusDetails = SSMcommandOut['StatusDetails']
SSMcommandOutput = SSMcommandOut['StandardOutputContent']
SSMcommandError = SSMcommandOut['StandardErrorContent']

print(f"\nSSM status: {SSMcommandOutStatus}")
print(f"SSM status details: {SSMcommandOutStatusDetails}")
print(f"SSM command outputs:\n\n{SSMcommandOutput}")
print(f"SSM command errors: {SSMcommandError}")


print(f"\n====ASG healthcheck and replace unhealthy tests=====")

match=re.findall(r'\bHealthCheck|ReplaceUnhealthy\b',spList)

if match:
    print(f"\nASG test skipped due to the following suspended processes:\n {match}")
else:

    responseDescribeASGPostChange = client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            asgName,
        ],
    )
    
    instancePostChange=responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances'][0]['InstanceId']
    instanceHealthPostChange=responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances'][0]['HealthStatus']
    instanceStatusPostChange=responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances'][0]['LifecycleState']
    print(f"Instance Id: {instancePostChange}")
    print(f"Instance Health {instanceHealthPostChange}")
    print(f"ASG Service State: {instanceStatusPostChange}")

    ec2Status = clientEC2.describe_instance_status(
        InstanceIds=[
        instancePostChange,
        ],
    )

    while not ec2Status['InstanceStatuses']:
        time.sleep(2)
        print(ec2Status['InstanceStatuses'])


    responseSetHealth = clientEC2.terminate_instances(
        InstanceIds=[
            instance,
        ],
        DryRun=False
    )

    print(f"\nWaiting for ASG to remove instance {instancePostChange}..")
    instanceList = []

    for item in responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances']:
        for k,v in item.items():
            if k == 'InstanceId':
                instanceList.append(v)

    #print(instanceList)

    timeout = time.time() + 60*3
    while instancePostChange in instanceList:
        del instanceList
        instanceList = []
        responseDescribeASGPostChange = client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[
                asgName,
            ],
        )
        
        for item in responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances']:
            for k,v in item.items():
                if k == 'InstanceId':
                    instanceList.append(v)
        #print(instanceList)
        time.sleep(2)
        if time.time() > timeout:
            sys.exit(f"\nASG healthcheck test failed, aborting")

        # instancePostChange=responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances'][0]['InstanceId']
        # instanceHealthPostChange=responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances'][0]['HealthStatus']
        # instanceStatusPostChange=responseDescribeASGPostChange['AutoScalingGroups'][0]['Instances'][0]['LifecycleState']

        # print(f"Instance Id: {instancePostChange}")
        # print(f"Instance Health {instanceHealthPostChange}")
        # print(f"ASG Service State: {instanceStatusPostChange}")
        
    print(f"\nASG healthcheck test passed")
    
# time.sleep(10)

responseDescribeASGCheck = clientCheck.describe_auto_scaling_groups(
    AutoScalingGroupNames=[
        asgName,
    ],
)

getASGdesiredCheck=responseDescribeASGCheck['AutoScalingGroups'][0]['DesiredCapacity']
getASGhealthyec2sCheck=responseDescribeASGCheck['AutoScalingGroups'][0]['Instances']

ASGhealthyListCheck = []

for item in getASGhealthyec2sCheck:
    for k, v in item.items():
        if k == 'HealthStatus':
            ASGHealthyListCheck = ASGhealthyListCheck.append(v)

if len(ASGhealthyListCheck) == getASGdesiredCheck:
    print("\n====Desired and current capacity matches====")
    print(f"{getASGdesiredCheck} : {len(ASGhealthyListCheck)}")
else:
    print("\nWaiting for the ASG to match the desired capacity...")
    timeout = time.time() + 60*3
    while len(ASGhealthyListCheck) != getASGdesiredCheck:
        del responseDescribeASGCheck

        responseDescribeASGCheck = clientCheck.describe_auto_scaling_groups(
            AutoScalingGroupNames=[
                asgName,
            ],
        )

        getASGdesiredCheck=responseDescribeASGCheck['AutoScalingGroups'][0]['DesiredCapacity']
        getASGhealthyec2sCheck=responseDescribeASGCheck['AutoScalingGroups'][0]['Instances']

        ASGhealthyListCheck = []

        for item in getASGhealthyec2sCheck:
            for k, v in item.items():
                if k == 'HealthStatus':
                    ASGHealthyListCheck = ASGhealthyListCheck.append(v)
        #print(f"{getASGdesiredCheck} : {len(ASGhealthyListCheck)}")
        if time.time() > timeout:
            sys.exit("ASG failed to match desired capacity, aborting")
        time.sleep(2)
    print("\nDesired and current capacity matches")
    print(f"{getASGdesiredCheck} : {len(ASGhealthyListCheck)}")


del responseEC2ops

responseDescribeASG = client.describe_auto_scaling_groups(
    AutoScalingGroupNames=[
        asgName,
    ],
)

instanceTestFinal=responseDescribeASG['AutoScalingGroups'][0]['Instances']

instanceListFinal = []

for item in instanceTestFinal:
    for k,v in item.items():
        if k == 'InstanceId':
            instaceListFinal = instanceListFinal.append(v)

responseEC2ops = clientEC2.describe_instance_status(
    InstanceIds=instanceList,
    IncludeAllInstances=True
)

InstanceCheckFinal=responseEC2ops['InstanceStatuses']

runningListFinal = []

for item in InstanceCheckFinal:
    for k,v in item.items():
        if k == 'InstanceState':
            for k2,v2 in v.items():
                if k2 == 'Name':
                    runningListFinal.append(v2)

runningTestFinal = [x for x in runningListFinal if 'running' != x]
print("\n====Ensuring all instances in the ASG are in a running state====")

time.sleep(10)
if len(runningTestFinal) > 0:
    timeout = time.time() + 60*3
    while len(runningTestFinal) > 0:
        #print(runningTestFinal)
        del responseEC2ops
        responseEC2ops = clientEC2.describe_instance_status(
        InstanceIds=instanceList,
        IncludeAllInstances=True
        )

        InstanceCheckFinal=responseEC2ops['InstanceStatuses']

        runningListFinal = []

        for item in InstanceCheckFinal:
            for k,v in item.items():
                if k == 'InstanceState':
                    for k2,v2 in v.items():
                        if k2 == 'Name':
                            runningListFinal.append(v2)

        runningTestFinal = [x for x in runningList if 'running' != x]
        if time.time() > timeout:
            sys.exit("====Not all ASG instances are in a running state, aborting====")

print("ASG instances are in the running state\n")

print ("==================================")
print ("====Completed regression tests====")
print ("==================================\n")
