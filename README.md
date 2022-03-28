# aws-regression-tests
Regression test specified AWS resources based on pre-written modules

#### Description
Execute regression testing against avaiable resources in AWS, such as specifying Auto Scaling Group, Load Balancers, and EC2s. This tool may also be incorporated into a CI/CD pipeline. Modules may be common to multiple cloud resources i.e., any resource using an Auto Scaling Group.

#### Intended Audience
* Developers
* Devops

#### Pre-requisites
* Python 3.7
* Running AWS Infrastructure according to the module

#### Usage

##### Help
`aws-regression-tests-*module*.py *Argument 1* *Argument 2*
 
#### Jenkins Pipeline Automation
 The approriate module is called by the Jenkins pipeline, contigent upon defined cloud resources.
 * For example, `Auto Scaling Group` based resources will load the `aws-regression-tests-asg.py` module.

#### Modules

##### Auto Scaling Group Module (aws-regression-tests-asg.py)
 
###### Actions performed
Ensure the desired capacity and number of instances running match and are in a healthy state. Perform application tests at the OS layer, take an instance out of service and check for proper instance replacement where the desired and number of running instances once again align.
 
###### Options

* Argument 1: Auto Scaling Group Name
* Argument 2: AWS Region

###### Examples

  * Regression test Auto Scaling Group 'al-test-am' in 'us-east-1' region
    * `aws-regression-test-asg al-test-am us-east-1`
