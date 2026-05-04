// Streaming fixed-point CINTAS starter RTL.
//
// This module is intentionally small and parameterized. It processes one
// selected feature per cycle, accumulates E1/E2 for one sample, updates a
// block-level max aggregator once every FEATURES inputs, and emits an alert
// once SAMPLES_PER_BLOCK samples have been consumed.

module cintas_stream #(
    parameter int FEATURES = 15,
    parameter int Q = 15,
    parameter int WIDTH = 32,
    parameter int ACC_WIDTH = 64,
    parameter int SAMPLES_PER_BLOCK = 250
) (
    input  logic                         clk,
    input  logic                         rst_n,
    input  logic                         valid_i,
    input  logic signed [WIDTH-1:0]      x_q_i,
    input  logic signed [WIDTH-1:0]      mu_q_i,
    input  logic signed [WIDTH-1:0]      gamma_q_i,
    input  logic signed [WIDTH-1:0]      w_q_i,
    input  logic signed [WIDTH-1:0]      lambda_q_i,
    input  logic signed [ACC_WIDTH-1:0]  tau_q_i,
    output logic                         ready_o,
    output logic                         decision_valid_o,
    output logic                         alert_o,
    output logic signed [ACC_WIDTH-1:0]  block_score_q_o
);

    localparam logic signed [WIDTH-1:0] ONE_Q = (1 <<< Q);

    logic [$clog2(FEATURES)-1:0] feature_idx;
    logic [$clog2(SAMPLES_PER_BLOCK)-1:0] sample_idx;

    logic signed [ACC_WIDTH-1:0] e1_acc_q;
    logic signed [ACC_WIDTH-1:0] e2_acc_q;
    logic signed [ACC_WIDTH-1:0] block_max_q;
    logic signed [ACC_WIDTH-1:0] e1_next_q;
    logic signed [ACC_WIDTH-1:0] e2_next_q;

    logic signed [2*WIDTH-1:0] centered_gamma_q2;
    logic signed [WIDTH-1:0] z_q;
    logic signed [WIDTH-1:0] abs_z_q;
    logic signed [2*WIDTH-1:0] z2_q2;
    logic signed [2*WIDTH-1:0] w_abs_q2;
    logic signed [3*WIDTH-1:0] w_z2_q3;
    logic signed [ACC_WIDTH-1:0] e1_term_q;
    logic signed [ACC_WIDTH-1:0] e2_term_q;
    logic signed [ACC_WIDTH-1:0] sample_score_q;
    logic signed [ACC_WIDTH-1:0] mix_e2_q;
    logic signed [ACC_WIDTH-1:0] mix_e1_q;

    assign ready_o = 1'b1;

    always_comb begin
        centered_gamma_q2 = (x_q_i - mu_q_i) * gamma_q_i;
        z_q = centered_gamma_q2 >>> Q;
        abs_z_q = z_q[WIDTH-1] ? -z_q : z_q;
        z2_q2 = z_q * z_q;
        w_abs_q2 = w_q_i * abs_z_q;
        w_z2_q3 = w_q_i * z2_q2;
        e1_term_q = w_abs_q2 >>> Q;
        e2_term_q = w_z2_q3 >>> (2 * Q);
        e1_next_q = e1_acc_q + e1_term_q;
        e2_next_q = e2_acc_q + e2_term_q;
        mix_e2_q = ((ONE_Q - lambda_q_i) * e2_next_q) >>> Q;
        mix_e1_q = (lambda_q_i * e1_next_q) >>> Q;
        sample_score_q = mix_e2_q + mix_e1_q;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            feature_idx <= '0;
            sample_idx <= '0;
            e1_acc_q <= '0;
            e2_acc_q <= '0;
            block_max_q <= '0;
            block_score_q_o <= '0;
            decision_valid_o <= 1'b0;
            alert_o <= 1'b0;
        end else begin
            decision_valid_o <= 1'b0;

            if (valid_i && ready_o) begin
                e1_acc_q <= e1_next_q;
                e2_acc_q <= e2_next_q;

                if (feature_idx == FEATURES - 1) begin
                    if (sample_score_q > block_max_q) begin
                        block_max_q <= sample_score_q;
                    end

                    e1_acc_q <= '0;
                    e2_acc_q <= '0;
                    feature_idx <= '0;

                    if (sample_idx == SAMPLES_PER_BLOCK - 1) begin
                        block_score_q_o <= (sample_score_q > block_max_q) ? sample_score_q : block_max_q;
                        alert_o <= ((sample_score_q > block_max_q) ? sample_score_q : block_max_q) >= tau_q_i;
                        decision_valid_o <= 1'b1;
                        block_max_q <= '0;
                        sample_idx <= '0;
                    end else begin
                        sample_idx <= sample_idx + 1'b1;
                    end
                end else begin
                    feature_idx <= feature_idx + 1'b1;
                end
            end
        end
    end

endmodule
