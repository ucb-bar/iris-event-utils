package genevent

import chisel3._
import chisel3.util._
import chisel3.experimental.{IntParam, StringParam}

// class GenEvent(eventName: String, instanceCnt: Int, dataWidth: Int) extends Module {
//   val io = IO(new Bundle {
//     val data = Input(UInt(dataWidth.W))
//     val parent = Input(UInt(64.U)) //Should be fixed for multi-parent if EventTag is changed from 64.U
//     val id = Input(UInt(64.U))
//     val valid = Input(Bool())
//   })
// }

class ClockModule extends Module {
  val io = IO(new Bundle {
    val out = Output(Bool())
  })
  io.out := clock.asBool
}
object GenEvent {
  var instance_ctr: Int = 0
  def apply(eventName: String, data: UInt, parent: Option[EventTag], id: Option[UInt] = None, valid: Bool = true.B): EventTag = {
    var new_id = Wire(UInt(64.W))
    val id_ctr = RegInit(0.U(64.W))
    id_ctr := id_ctr + 1.U
    // new_id := Cat(instance_ctr.asUInt(32.W), id_ctr)
    new_id := (instance_ctr.asUInt(32.W) << 32) ^ id_ctr //Pseudo hash function
    val GenEventDPI = Module(new GenEventBlackBox(eventName))
    val ClockModule = Module(new ClockModule())
    GenEventDPI.io.clock := ClockModule.io.out
    if (id.isDefined) {
      GenEventDPI.io.id := id.get.pad(64)
    } else {
      GenEventDPI.io.id := new_id
    }
    if (parent.isDefined) {
      GenEventDPI.io.parent := parent.get.id.pad(64)
    } else {
      GenEventDPI.io.parent := 0.U
    }
    GenEventDPI.io.cycle := id_ctr
    GenEventDPI.io.data := data
    GenEventDPI.io.valid := valid

    // if (parent.isDefined) {
    //   if (id.isDefined) {
    //     printf(cf"{\"id\": \"0x${id.get}%x\", \"parents\": \"0x${parent.get.id}%x\", \"cycle\": \"$id_ctr\", \"event_name\": \"$eventName\", \"data\": \"0x$data%x\"}\n")
    //   } else {
    //     printf(cf"{\"id\": \"0x$new_id%x\", \"parents\": \"0x${parent.get.id}%x\", \"cycle\": \"$id_ctr\", \"event_name\": \"$eventName\", \"data\": \"0x$data%x\"}\n")
    //   }
    // } else {
    //   if (id.isDefined) {
    //     printf(cf"{\"id\": \"0x${id.get}%x\", \"parents\": \"None\", \"cycle\": \"$id_ctr\", \"event_name\": \"$eventName\", \"data\": \"0x$data%x\"}\n")
    //   } else {
    //     printf(cf"{\"id\": \"0x$new_id%x\", \"parents\": \"None\", \"cycle\": \"$id_ctr\", \"event_name\": \"$eventName\", \"data\": \"0x$data%x\"}\n")
    //   }
    // }
    
    instance_ctr += 1
    return EventTag(new_id)
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
    val id = Input(UInt(64.W))
    val parent = Input(UInt(64.W))
    val cycle = Input(UInt(64.W))
    val data = Input(UInt(64.W))
    val valid = Input(Bool())})
  addResource("/vsrc/GenEventDPI.v")
  addResource("/csrc/GenEventDPI.cc")
  }