Iris Event Annotation Tools
=======================
Iris (uArchDB) provides a set of tools for extracting microarchitecture events and data in RTL for debugging and analysis. 

## GenEvent Module
The GenEvent module written in CHISEL HDL and allows users to annotate their own modules to log timing and signal data at an event level. GenEvent implements a DPI interface for efficient logging.
### Importing GenEvent
The GenEvent module can be imported by adding
```scala
import genevent._
```
to each project file where it is instantiated.

To build GenEvent, add `iris_event_utils` to the dependecies of your project in the top-level Chipyard `build.sbt`.

For example, `iris_event_utils` added to Sodor:
```scala
lazy val sodor = (project in file("generators/riscv-sodor"))
  .dependsOn(rocketchip, iris_event_utils)
  .settings(libraryDependencies ++= rocketLibDeps.value)
  .settings(commonSettings)
```
### Adding GenEvent to a Module
Each GenEvent instance has a
- Event Name string `eventName`
- 64 bit Data input `data`
- Optional Valid input `valid`
- Optional 64 bit Parent Tag ID input `parent`
- Optional 64 bit Instance Tag ID input `id`
- Tag ID output

A GenEvent instance records the `eventName`, a unique tag, cycle, `parent` tag, and `data` for an event every cycle when `valid` is high (`valid` is always high if no `valid` input is specified). 

#### EventTag and Event Graph
EventTag's are 64 bit values that uniquely identify an event in the log. Each GenEvent instance generates a unique tag output signal every cycle that is logged and can also be passed to the `parent` input of other GenEvent instances through RTL to form a parent-child relationship. Multiple GenEvent instances can be chained to form a graph of dependent events. 

Optionally, a tag can be passed to the `id` input. This will replace the uniquely generated tag in the log and can be useful if there is already a unique identifier in the RTL such as a transaction ID. The same ID can be passed to multiple GenEvent instances to chain the events chronologically.

An example of a GenEvent declaration:
```scala
val tag_reg = Reg(new EventTag)
tag_reg := GenEvent("event_name", event_data, Some(parent_reg), None, event_valid)
```
Here, `tag_reg` registers the output of the `GenEvent`. A susbsequent `GenEvent` can use `tag_reg` in place of `parent_reg` as shown above to connect the two events. `id` is `None` in this event.

#### Output Log Format
GenEvent outputs a plain text log with 
```
event_name <id> <parent> <cycle> <data>
```
### Examples
Currently, Sodor, Rocket, and Gemmini have GenEvent annotations. More designs are on the way!

## iris.py Script

## Konata

## 

