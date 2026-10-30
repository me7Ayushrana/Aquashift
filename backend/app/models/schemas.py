"""Pydantic schemas for request and response models."""
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(default="ok", description="Service health status")


class CropPredictionRequest(BaseModel):
    """Request payload for single-crop prediction."""
    crop_id: str = Field(..., description="Crop identifier (paddy, wheat, maize, pulses, millets)")
    rainfall_scenario: str = Field(..., description="Rainfall scenario (normal, deficit, severe_deficit, surplus)")
    water_availability_ratio: float = Field(
        ...,
        ge=0.05,
        le=2.0,
        description="Relative irrigation water availability ratio (e.g. 0.80 for -20%, 0.20 for -80%)",
    )

    @field_validator("crop_id")
    @classmethod
    def normalize_crop_id(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("rainfall_scenario")
    @classmethod
    def normalize_scenario(cls, v: str) -> str:
        return v.strip().lower()


class CropPrediction(BaseModel):
    """Predicted yield and irrigation water demand with indicative uncertainty margins.

    Note on Terminology:
    - Uncertainty ranges (`yield_range_lower/upper`, `water_range_lower/upper`) represent
      approximate error margins based on validation residual spread (±1.96 * RMSE). They are
      indicative demo uncertainty estimates, NOT statistically calibrated 95% confidence intervals.
    - The 0.05 t/ha lower clamp is a numerical stability floor for downstream mathematical
      programming, NOT an agronomic harvest guarantee. Total crop failure (0 t/ha) is possible
      under catastrophic drought.
    """
    crop_id: str = Field(..., description="Crop identifier")
    crop_name: str = Field(..., description="Crop display name")
    predicted_yield_t_ha: float = Field(
        ...,
        ge=0.0,
        description="Predicted yield in tonnes/hectare (subject to 0.05 t/ha numerical solver floor)",
    )
    yield_range_lower: float = Field(
        ...,
        ge=0.0,
        description="Approximate lower error margin bound for yield (based on residual spread, clamped to 0.05 t/ha numerical floor)",
    )
    yield_range_upper: float = Field(
        ...,
        ge=0.0,
        description="Approximate upper error margin bound for yield (based on residual spread)",
    )
    predicted_water_demand_m3_ha: float = Field(
        ...,
        ge=0.0,
        description="Predicted seasonal supplementary irrigation requirement in m³/ha",
    )
    water_range_lower: float = Field(
        ...,
        ge=0.0,
        description="Approximate lower error margin bound for water demand (clamped to 200 m³/ha numerical floor)",
    )
    water_range_upper: float = Field(
        ...,
        ge=0.0,
        description="Approximate upper error margin bound for water demand",
    )


class BatchPredictionRequest(BaseModel):
    """Request payload for multi-crop prediction under a scenario."""
    rainfall_scenario: str = Field(..., description="Rainfall scenario")
    water_availability_ratio: float = Field(
        ...,
        ge=0.05,
        le=2.0,
        description="Relative irrigation water availability ratio",
    )
    crops: Optional[List[str]] = Field(
        None,
        description="Optional list of crop IDs to predict. If omitted, predicts for all configured crops.",
    )

    @field_validator("rainfall_scenario")
    @classmethod
    def normalize_scenario(cls, v: str) -> str:
        return v.strip().lower()


class BatchPredictionResponse(BaseModel):
    """Batch prediction response containing predictions for all requested crops."""
    rainfall_scenario: str
    water_availability_ratio: float
    predictions: Dict[str, CropPrediction]


# =============================================================================
# Optimization Schemas (Phase 3)
# =============================================================================

class OptimizationMode(str, Enum):
    """Optimization solver mode."""
    WEIGHTED = "weighted"
    LEXICOGRAPHIC = "lexicographic"


class OptimizationWeights(BaseModel):
    """Normalized or raw user weights for the weighted optimization mode."""
    water: float = Field(default=1.0, ge=0.0, description="Priority weight for water shortfall")
    food: float = Field(default=1.0, ge=0.0, description="Priority weight for food shortfall")
    income: float = Field(default=1.0, ge=0.0, description="Priority weight for income shortfall")

    @model_validator(mode="after")
    def validate_positive_weights(self) -> "OptimizationWeights":
        if self.water + self.food + self.income <= 0:
            raise ValueError("At least one optimization weight must be strictly positive.")
        return self


class CropAllocationResult(BaseModel):
    """Hectare allocation and resulting agronomic/economic outputs for a single crop."""
    crop_id: str = Field(..., description="Crop identifier")
    crop_name: str = Field(..., description="Crop display name")
    allocated_ha: float = Field(..., ge=0.0, description="Allocated land area in hectares")
    land_percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total land")
    predicted_yield_t_ha: float = Field(..., ge=0.0, description="Predicted crop yield in t/ha")
    predicted_water_demand_m3_ha: float = Field(..., ge=0.0, description="Predicted seasonal irrigation demand in m³/ha")
    production_tonnes: float = Field(..., ge=0.0, description="Total production in metric tonnes")
    production_quintals: float = Field(..., ge=0.0, description="Total production in quintals (1 tonne = 10 quintals)")
    gross_revenue_inr: float = Field(..., ge=0.0, description="Gross market revenue in INR")
    cultivation_cost_inr: float = Field(..., ge=0.0, description="Total cultivation cost in INR")
    net_income_inr: float = Field(..., description="Net farmer income in INR (gross revenue - cultivation cost)")
    food_calories_kcal: float = Field(..., ge=0.0, description="Total food energy in kcal")


class MetricComparison(BaseModel):
    """Side-by-side KPI card comparison between baseline and optimized plans."""
    metric_name: str = Field(..., description="Human-readable KPI name")
    unit: str = Field(..., description="Measurement unit (e.g. m³, kcal, ₹)")
    baseline_value: float = Field(..., description="Baseline reference value")
    optimized_value: float = Field(..., description="Optimized plan value")
    delta_value: float = Field(..., description="Absolute change (optimized - baseline)")
    delta_percentage: float = Field(..., description="Percentage change relative to baseline")
    target_value: Optional[float] = Field(default=None, description="Scenario target or budget limit")
    shortfall: float = Field(default=0.0, ge=0.0, description="Unmet shortfall (slack) against target")
    status: str = Field(..., description="Status tier: 'green', 'amber', or 'red'")


class BindingConstraint(BaseModel):
    """Information on active binding constraints and their dual values."""
    name: str = Field(..., description="Constraint identifier")
    constraint_type: str = Field(..., description="Type: hard_land, hard_crop_min, hard_crop_max, soft_water, soft_food, soft_income")
    limit_value: float = Field(..., description="Right-hand side bound limit")
    achieved_value: float = Field(..., description="Achieved activity value")
    is_binding: bool = Field(..., description="Whether constraint is binding at tolerance")
    dual_value: Optional[float] = Field(default=None, description="GLOP solver dual value")
    sensitivity_label: str = Field(
        default="local_model_sensitivity",
        description="Explicit label indicating value is a local model derivative, NOT a real-world market price",
    )
    interpretation: Optional[str] = Field(default=None, description="Human-readable mathematical interpretation")


class LocalModelSensitivity(BaseModel):
    """Marginal objective sensitivity to key scenario parameters."""
    parameter_name: str = Field(..., description="Constrained resource parameter")
    marginal_value: float = Field(..., description="Local derivative value")
    unit: str = Field(..., description="Rate of change unit")
    interpretation: str = Field(..., description="Contextual explanation labeled as local model sensitivity")


class BottleneckRanking(BaseModel):
    """Prioritized bottleneck diagnosis entry."""
    rank: int = Field(..., ge=1, le=3, description="Priority rank (1 = most critical)")
    dimension: str = Field(..., description="Resource dimension: 'Water', 'Income', or 'Food'")
    severity: str = Field(..., description="Severity level: 'Critical', 'High', 'Moderate', or 'Satisfied'")
    slack_amount: float = Field(..., ge=0.0, description="Absolute slack shortfall")
    slack_percentage: float = Field(..., ge=0.0, description="Shortfall percentage relative to target or budget")
    explanation: str = Field(..., description="Narrative diagnostic reason")


class DiagnosisReport(BaseModel):
    """Comprehensive diagnostic breakdown of resource bottlenecks and missed targets."""
    all_targets_met: bool = Field(..., description="True if water, food, and income targets are all met without slack")
    missed_targets: List[str] = Field(default_factory=list, description="List of dimensions with non-zero shortfall")
    binding_constraints: List[str] = Field(default_factory=list, description="Names of all binding constraints")
    primary_bottleneck: Optional[str] = Field(default=None, description="Most severely binding resource dimension")
    bottleneck_ranking: List[BottleneckRanking] = Field(default_factory=list, description="Ranked list of bottlenecks")
    narrative_diagnosis: str = Field(..., description="Clear explanation of why targets cannot be simultaneously met")


class OptimizationRequest(BaseModel):
    """Scenario inputs for crop-allocation optimization."""
    total_land_ha: float = Field(default=10.0, gt=0.0, description="Available farm land in hectares")
    water_budget_m3: Optional[float] = Field(default=None, ge=0.0, description="Available seasonal water budget in m³")
    water_budget_reduction_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Percentage reduction in water budget relative to baseline (e.g. 20 for -20%)",
    )
    food_target_kcal: Optional[float] = Field(default=None, ge=0.0, description="Target nutritional calories in kcal")
    food_target_increase_pct: Optional[float] = Field(
        default=None,
        ge=-100.0,
        description="Percentage change in food target relative to baseline (e.g. 10 for +10%)",
    )
    income_target_inr: Optional[float] = Field(default=None, ge=0.0, description="Target net income in INR")
    income_target_increase_pct: Optional[float] = Field(
        default=None,
        ge=-100.0,
        description="Percentage change in income target relative to baseline (e.g. 50 for +50%)",
    )
    rainfall_scenario: str = Field(default="normal", description="Rainfall scenario (normal, deficit, severe_deficit, surplus)")
    water_availability_ratio: Optional[float] = Field(
        default=None,
        ge=0.05,
        le=2.0,
        description="Relative irrigation availability ratio (0.05 to 2.0). If omitted, inferred from water budget.",
    )
    selected_crops: Optional[List[str]] = Field(
        default=None,
        description="List of crop IDs allowed for allocation. Defaults to all 5 crops.",
    )
    optimization_mode: OptimizationMode = Field(
        default=OptimizationMode.WEIGHTED,
        description="Optimization mode: weighted or lexicographic",
    )
    weights: Optional[OptimizationWeights] = Field(
        default=None,
        description="User priority weights for weighted mode (water, food, income)",
    )
    water_first_priority: bool = Field(
        default=False,
        description="If True, strictly prioritizes water reduction (or activates lexicographic solve)",
    )

    @field_validator("rainfall_scenario")
    @classmethod
    def normalize_scenario(cls, v: str) -> str:
        return v.strip().lower()


class OptimizationResponse(BaseModel):
    """Complete structured output from the OR-Tools optimization engine."""
    solver_status: str = Field(..., description="Solver termination status: OPTIMAL, FEASIBLE, or INFEASIBLE_HARD_CONSTRAINTS")
    optimization_mode: str = Field(..., description="Solver mode executed: weighted or lexicographic")
    total_land_ha: float = Field(..., ge=0.0, description="Total allocated land area in hectares")
    allocations: List[CropAllocationResult] = Field(..., description="Crop-by-crop allocation and outputs")
    
    # Water accounting
    total_water_use_m3: float = Field(..., ge=0.0, description="Total predicted seasonal water consumption in m³")
    water_budget_m3: float = Field(..., ge=0.0, description="Allocated seasonal water budget in m³")
    water_slack_m3: float = Field(..., ge=0.0, description="Water shortfall/deficit exceeding budget in m³")
    water_shortfall_pct: float = Field(..., ge=0.0, description="Water shortfall percentage relative to budget")

    # Food accounting
    total_food_kcal: float = Field(..., ge=0.0, description="Total food caloric production in kcal")
    food_target_kcal: float = Field(..., ge=0.0, description="Target food caloric production in kcal")
    food_slack_kcal: float = Field(..., ge=0.0, description="Food shortfall below target in kcal")
    food_shortfall_pct: float = Field(..., ge=0.0, description="Food shortfall percentage relative to target")

    # Financial accounting
    total_gross_revenue_inr: float = Field(..., ge=0.0, description="Total gross crop revenue in INR")
    total_cultivation_cost_inr: float = Field(..., ge=0.0, description="Total cost of cultivation in INR")
    total_net_income_inr: float = Field(..., description="Total net farm income in INR")
    income_target_inr: float = Field(..., ge=0.0, description="Target net farm income in INR")
    income_slack_inr: float = Field(..., ge=0.0, description="Income shortfall below target in INR")
    income_shortfall_pct: float = Field(..., ge=0.0, description="Income shortfall percentage relative to target")

    # Diagnostics and sensitivity
    binding_constraints: List[BindingConstraint] = Field(default_factory=list, description="Active binding constraints")
    local_sensitivities: List[LocalModelSensitivity] = Field(default_factory=list, description="Local model derivatives")
    baseline_comparison: Dict[str, MetricComparison] = Field(default_factory=dict, description="Baseline vs optimized KPIs")
    diagnosis: DiagnosisReport = Field(..., description="Bottleneck diagnosis report")
    objective_value: float = Field(..., description="Optimal objective function value")
    solve_time_ms: float = Field(..., ge=0.0, description="Solver execution time in milliseconds")


class StressTestResponse(BaseModel):
    """Output of the extreme-scenario stress test comparing strict vs soft recovery solve."""
    strict_solve_status: str = Field(..., description="Status of strict solve: INFEASIBLE or OPTIMAL")
    strict_solve_message: str = Field(..., description="Explanation of strict solve failure")
    recovery_solve_status: str = Field(..., description="Status of soft recovery solve")
    closest_feasible_plan: OptimizationResponse = Field(..., description="Optimal closest-feasible crop plan")
    tradeoff_analysis: str = Field(..., description="Detailed explanation of necessary trade-offs and recovery plan")
    individual_feasibility: Dict[str, bool] = Field(
        default_factory=dict,
        description="Whether each individual target is achievable under hard land constraints alone",
    )
    joint_feasibility: Dict[str, bool] = Field(
        default_factory=dict,
        description="Whether combinations of targets are jointly achievable",
    )
    target_boundaries: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Physical achievable extremes vs target limits (min water, max food, max income)",
    )


class OptimizationValidationResult(BaseModel):
    """Validation result for pre-solve hard constraint checks."""
    is_valid: bool = Field(..., description="True if hard constraints are mathematically feasible")
    error_code: Optional[str] = Field(default=None, description="Error code identifier")
    message: Optional[str] = Field(default=None, description="Detailed validation error message")
    conflicting_constraints: List[str] = Field(default_factory=list, description="List of conflicting constraint names")
