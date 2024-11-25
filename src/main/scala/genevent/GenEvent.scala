package genevent

import chisel3._
import chisel3.util._
import chisel3.experimental.{IntParam, StringParam}

//GenEventModule is a wrapper for GenEventBlackBox
class GenEventModule(val eventName: String) extends Module {
  val io = IO(new Bundle {
    val id = Input(UInt(64.W))
    val parent = Input(UInt(64.W)) 
    val cycle = Input(UInt(64.W))
    val data = Input(UInt(64.W))
    val valid = Input(UInt(64.W))
  })
  //Instatiate Verilog BlackBox and connect IOs
  val GenEventDPI = Module(new GenEventBlackBox(eventName))
  GenEventDPI.io.clock := clock.asBool
  GenEventDPI.io.reset := reset.asBool
  GenEventDPI.io.id := io.id
  GenEventDPI.io.parent := io.parent
  GenEventDPI.io.cycle := io.cycle
  GenEventDPI.io.data := io.data
  GenEventDPI.io.valid := io.valid
}
//GenEvent apply instantiates a GenEventModule which instantiates GenEventBlackBox
object GenEvent {
  var instance_ctr: Int = 1
  def apply(eventName: String, data: UInt, valid: Bool, parent: Option[EventTag], id: Option[UInt] = None): EventTag = {
    var newID = Wire(UInt(64.W))
    var IDreg = Reg(UInt(64.W))
    val cycleCounter = RegInit(0.U(64.W))
    cycleCounter := cycleCounter + 1.U
    newID := Cat(instance_ctr.asUInt(16.W), cycleCounter(47, 0)) //Maximum of 2^16 GenEvent instances. Consider generating ID entirely in DPI function

    //Instantiate GenEventModule 
    val GenEventModule = Module(new GenEventModule(eventName))
    if (id.isDefined) {
      GenEventModule.io.id := id.get.pad(64)
    } else {
      GenEventModule.io.id := newID
    }
    if (parent.isDefined) {
      GenEventModule.io.parent := parent.get.id.pad(64)
    } else {
      GenEventModule.io.parent := 0.U
    }
    GenEventModule.io.cycle := cycleCounter
    GenEventModule.io.data := data
    GenEventModule.io.valid := valid

    //Increment global instance_ctr
    instance_ctr += 1

    when (valid) {
      IDreg := newID
    }
    return EventTag(IDreg)
  }
}
class EventTag extends Bundle {
  val id = UInt(64.W)
}
object EventTag {
  def apply(id: UInt): EventTag = {
    val tag = Wire(new EventTag)
    tag.id := id
    return tag
  }
}

class GenEventBlackBox(
  event_name: String
) extends BlackBox(Map(
    "EVENT_NAME" -> StringParam(event_name)
  )) with HasBlackBoxResource {

  val io = IO(new Bundle {
    val clock = Input(Bool())
    val reset = Input(Bool())
    val id = Input(UInt(64.W))
    val parent = Input(UInt(64.W))
    val cycle = Input(UInt(64.W))
    val data = Input(UInt(64.W))
    val valid = Input(Bool())})
  addResource("/vsrc/GenEventDPI.v")
  addResource("/csrc/GenEventDPI.cc")
  }