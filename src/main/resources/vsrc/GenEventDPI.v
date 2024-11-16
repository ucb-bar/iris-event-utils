import "DPI-C" function void gen_event_export(input string event_name,
                                              input longint id,
                                              input longint parent,
                                              input longint cycle,
                                              input longint data);
module GenEventBlackBox #(
                        parameter EVENT_NAME)
                        (input clock,
                        input [63:0] id,
                        input [63:0] parent,
                        input [63:0] cycle,
                        input [63:0] data,
                        input valid
);
    always @(posedge clock) begin
        if (valid) begin
            gen_event_export(EVENT_NAME, id, parent, cycle, data);
        end
    end

endmodule