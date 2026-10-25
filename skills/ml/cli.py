"""File-based adapters for the optional machine-learning helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills.cli.io import (
    check_output,
    data_manager,
    factor_function,
    frame_summary,
    json_safe,
    load_panel,
    read_frame,
    resolve_symbols,
    write_frame,
)
from skills.cli.models import (
    Artifact,
    CLIError,
    CLIModel,
    CommandResult,
    OutputOptions,
    PanelSource,
)
from skills.cli.registry import Command


def _has_panel_source(args) -> bool:
    return args.panel is not None or bool(args.symbols) or args.symbols_file is not None


def _close_returns(args):
    """Close-to-close returns (date x symbol); the first, always empty row is dropped."""
    close = load_panel(args)["close"].unstack("symbol").sort_index()
    return close.pct_change(fill_method=None).iloc[1:]


class MLFactorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicator: str | None = Field(default=None, description="Public skills.compute indicator name.")
    function: str | None = Field(
        default=None, description="Importable module:name factor callable."
    )
    params: dict = Field(default_factory=dict, description="Factor keyword arguments.")
    name: str | None = Field(
        default=None, description="Feature name; defaults to the function name."
    )

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.indicator) == bool(self.function):
            raise ValueError("Exactly one of indicator or function is required")
        return self


class FactorRankInput(PanelSource, OutputOptions):
    output: Path = Field(description="Destination rank table (date by symbol, values in [0, 1]).")
    factors: list[MLFactorItem] = Field(description="Feature factors, each called per symbol.")
    model: str = Field(
        default="xgboost", description="PyCaret regression model id, e.g. xgboost or rf."
    )
    target_forward: int = Field(default=1, gt=0, description="Forward return horizon of the label.")
    train_mode: Literal["fixed", "rolling"] = Field(
        default="rolling", description="fixed: one split; rolling: expanding retraining."
    )
    train_ratio: float = Field(default=0.7, gt=0, lt=1, description="fixed mode training fraction.")
    train_window: int = Field(default=120, gt=0, description="rolling mode initial training days.")
    retrain_freq: int = Field(
        default=20, gt=0, description="rolling mode retraining interval in days."
    )
    n_folds: int = Field(default=5, gt=1, description="PyCaret cross-validation folds.")
    pycaret_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Extra keyword arguments for PyCaret setup()."
    )
    importance_output: Path | None = Field(
        default=None, description="Optional feature importance table."
    )

    @model_validator(mode="after")
    def check_factors(self):
        if not self.factors:
            raise ValueError("factors cannot be empty")
        return self


class FactorRankData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Rank table rows.")
    columns: list[str] = Field(description="Rank table symbols.")
    oos_start_date: str | None = Field(description="First out-of-sample date.")
    evaluation: dict[str, Any] = Field(description="MLFactorEngine.get_eval_summary().")


def factor_rank(args: FactorRankInput) -> CommandResult:
    from skills.ml.ml_factor import MLFactorEngine

    if args.importance_output and (
        args.importance_output.expanduser().resolve() == args.output.expanduser().resolve()
    ):
        raise ValueError("output and importance_output must be different files")
    for path in (args.output, args.importance_output):
        if path:
            check_output(path, overwrite=args.overwrite, data_root=args.data_root)
    configs = []
    for item in args.factors:
        config = {"func": factor_function(item.indicator, item.function), "kwargs": item.params}
        if item.name:
            config["name"] = item.name
        configs.append(config)
    engine = MLFactorEngine(
        data=load_panel(args),
        factor_configs=configs,
        model_type=args.model,
        target_forward=args.target_forward,
        train_mode=args.train_mode,
        train_ratio=args.train_ratio,
        train_window=args.train_window,
        retrain_freq=args.retrain_freq,
        n_folds=args.n_folds,
        pycaret_kwargs=args.pycaret_kwargs,
    )
    rank = engine.generate()
    importance = None
    if args.importance_output:
        if engine.feature_importance_df is None:
            raise CLIError(
                "INVALID_INPUT",
                f"model {args.model!r} reports no feature importance; drop --importance-output",
            )
        importance = engine.get_feature_importance()
    evaluation = json_safe(engine.get_eval_summary())
    artifacts = [
        write_frame(
            rank, args.output, overwrite=args.overwrite, data_root=args.data_root, name="rank"
        )
    ]
    if importance is not None:
        artifacts.append(
            write_frame(
                importance,
                args.importance_output,
                overwrite=args.overwrite,
                data_root=args.data_root,
                name="importance",
            )
        )
    oos = getattr(engine, "oos_start_date", None)
    return CommandResult(
        data=FactorRankData(
            rows=len(rank),
            columns=[str(column) for column in rank.columns],
            oos_start_date=None if oos is None else str(oos),
            evaluation=evaluation,
        ),
        artifacts=artifacts,
    )


class LassoInput(PanelSource, OutputOptions):
    output: Path = Field(description="Destination tracking weights (date by symbol).")
    returns: Path | None = Field(
        default=None,
        description="Candidate daily returns (date by symbol); otherwise close-to-close "
        "returns of the panel source.",
    )
    index_symbol: str | None = Field(
        default=None, description="Target index symbol read from the same store and frequency."
    )
    index_returns: Path | None = Field(
        default=None, description="Dated table holding the target index returns."
    )
    index_column: str = Field(default="return", description="Return column of index_returns.")
    lookback: int = Field(default=120, gt=0, description="Training window in trading days.")
    alpha: float = Field(default=1e-6, gt=0, description="LASSO strength; larger is sparser.")
    min_periods: int = Field(default=60, gt=0, description="Minimum samples before weights.")
    rebalance_freq: Literal["D", "W", "M"] = Field(default="M", description="Refit frequency.")
    max_weight: float = Field(default=0.3, gt=0, le=1, description="Cap per candidate.")

    @model_validator(mode="after")
    def one_index(self):
        if (self.index_symbol is None) == (self.index_returns is None):
            raise ValueError("Exactly one of index_symbol or index_returns is required")
        return self


class WeightsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Number of dates.")
    columns: list[str] = Field(description="Symbol columns.")
    start: str | None = Field(description="First date.")
    end: str | None = Field(description="Last date.")
    preview: list[dict] = Field(description="First weight rows.")


def lasso(args: LassoInput) -> CommandResult:
    from skills.ml.lasso_tracker import lasso_track

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    if args.returns is not None:
        candidates = read_frame(args.returns)
    elif _has_panel_source(args):
        candidates = _close_returns(args)
    else:
        raise CLIError("INVALID_INPUT", "provide --returns or a panel source for the candidates")
    if args.index_returns is not None:
        table = read_frame(args.index_returns)
        if args.index_column not in table:
            raise ValueError(f"index_returns requires column {args.index_column!r}")
        index = table[args.index_column]
    else:
        source = PanelSource(
            symbols=resolve_symbols([args.index_symbol]),
            frequency=args.frequency,
            data_root=args.data_root,
            start=args.start,
            end=args.end,
        )
        index = _close_returns(source).iloc[:, 0]
    weights = lasso_track(
        candidates,
        index,
        lookback=args.lookback,
        alpha=args.alpha,
        min_periods=args.min_periods,
        rebalance_freq=args.rebalance_freq,
        max_weight=args.max_weight,
    )
    artifact = write_frame(
        weights, args.output, overwrite=args.overwrite, data_root=args.data_root, name="weights"
    )
    return CommandResult(
        data=WeightsData(**frame_summary(weights, preview=args.preview)), artifacts=[artifact]
    )


class FoldsInput(PanelSource):
    table: Path | None = Field(
        default=None,
        description="Dated table whose eob dates define the calendar; otherwise the panel source.",
    )
    min_train: int = Field(default=250, gt=0, description="Dates before the first retrain.")
    retrain_step: int = Field(default=126, gt=0, description="Dates predicted per fold.")
    purge: int = Field(default=20, ge=0, description="Training dates removed before each fold.")


class FoldsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dates: int = Field(description="Calendar length.")
    folds: list[dict] = Field(
        description="fold_id, retrain_idx, purge and the first, last and count of train and "
        "predict dates."
    )


def folds(args: FoldsInput) -> CommandResult:
    import pandas as pd

    from skills.ml.walk_forward import expanding_purged_folds

    if args.table is not None:
        frame = read_frame(args.table)
        index = frame.index
        dates = index.get_level_values("eob") if "eob" in (index.names or []) else index
    elif _has_panel_source(args):
        dates = load_panel(args).index.get_level_values("eob")
    else:
        raise CLIError("INVALID_INPUT", "provide --table or a panel source")
    calendar = pd.DatetimeIndex(pd.unique(pd.DatetimeIndex(dates))).sort_values()
    result = expanding_purged_folds(
        calendar, min_train=args.min_train, retrain_step=args.retrain_step, purge=args.purge
    )
    rows = [
        {
            "fold_id": fold.fold_id,
            "retrain_idx": fold.retrain_idx,
            "purge": fold.purge,
            "train_start": fold.train_dates[0],
            "train_end": fold.train_dates[-1],
            "train_dates": len(fold.train_dates),
            "pred_start": fold.pred_dates[0],
            "pred_end": fold.pred_dates[-1],
            "pred_dates": len(fold.pred_dates),
        }
        for fold in result
    ]
    return CommandResult(data=FoldsData(dates=len(calendar), folds=json_safe(rows)))


class PcaPredictInput(OutputOptions):
    output: Path = Field(description="Destination predictions table with a prediction column.")
    train: Path = Field(description="Training table with feature columns and the target.")
    predict: Path = Field(description="Table of rows to predict, holding the same features.")
    target_col: str = Field(description="Target column of the training table.")
    feature_cols: list[str] = Field(
        default_factory=list,
        description="Ordered feature columns; defaults to every training column except the target.",
    )
    model: Literal["ols", "lasso", "rf", "xgboost"] = Field(
        description="make_regressor model with its frozen defaults."
    )
    n_pca: int = Field(default=50, gt=0, description="Maximum PCA components fit on train only.")
    random_state: int = Field(default=42, description="PCA and model random seed.")
    rf_n_jobs: int | None = Field(
        default=None, gt=0, description="Random forest workers; defaults to all cores."
    )


class PcaPredictData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Predicted rows.")
    features: int = Field(description="Input feature count.")
    components: int = Field(description="PCA components used.")
    pca_explained_variance_sum: float = Field(description="Train explained variance ratio sum.")


def pca_predict(args: PcaPredictInput) -> CommandResult:
    import numpy as np
    import pandas as pd

    from skills.ml.pca_fold import fit_fold_transform, make_regressor

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    train, predict = read_frame(args.train), read_frame(args.predict)
    if args.target_col not in train:
        raise ValueError(f"train requires target column {args.target_col!r}")
    features = args.feature_cols or [column for column in train if column != args.target_col]
    if not features or len(set(features)) != len(features):
        raise ValueError("feature columns must be unique and nonempty")
    for name, frame in (("train", train), ("predict", predict)):
        missing = [column for column in features if column not in frame]
        if missing:
            raise ValueError(f"{name} is missing feature columns: {missing}")
    transform = fit_fold_transform(
        train[features].to_numpy(dtype=np.float64),
        predict[features].to_numpy(dtype=np.float64),
        n_pca=args.n_pca,
        random_state=args.random_state,
    )
    model = make_regressor(args.model, random_state=args.random_state, rf_n_jobs=args.rf_n_jobs)
    model.fit(transform.train_X, train[args.target_col].to_numpy(dtype=np.float64))
    result = pd.DataFrame({"prediction": model.predict(transform.pred_X)}, index=predict.index)
    artifact = write_frame(
        result, args.output, overwrite=args.overwrite, data_root=args.data_root, name="predictions"
    )
    return CommandResult(
        data=PcaPredictData(
            rows=len(result),
            features=len(features),
            components=int(transform.train_X.shape[1]),
            pca_explained_variance_sum=transform.pca_explained_variance_sum,
        ),
        artifacts=[artifact],
    )


def _namespace(value: str) -> str:
    if not value or value in {".", ".."} or any(char in value for char in "/\\\0"):
        raise ValueError(f"Invalid model namespace: {value!r}")
    return value


class TrainInput(CLIModel):
    train: Path = Field(description="Training table with feature columns and the target.")
    target: str = Field(default="label", description="Target column.")
    task: Literal["classification", "regression"] = Field(
        default="classification", description="MLEngine task."
    )
    model_name: str = Field(default="xgboost", description="PyCaret model id, e.g. xgboost or lr.")
    normalize: str = Field(default="zscore", description="PyCaret normalize method.")
    pca_components: int | None = Field(
        default=None, gt=0, description="PyCaret PCA components; omitted disables PCA."
    )
    session_id: int = Field(default=369, description="PyCaret random seed.")
    n_jobs: int = Field(default=1, gt=0, description="PyCaret parallel jobs.")
    create_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra create_model arguments; omitted uses MLEngine's deterministic defaults.",
    )
    namespace: str = Field(description="Registry namespace under data/models.")
    data_root: Path | None = Field(
        None, description="Managed data root; otherwise QUANTSPACE_DATA_ROOT or repository data/."
    )
    write: bool = Field(
        default=False, description="Train and save to the registry; otherwise return a plan."
    )


class TrainData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dry_run: bool = Field(description="True when nothing was trained or written.")
    namespace: str = Field(description="Registry namespace.")
    registry_dir: str = Field(description="Namespace directory under the data root.")
    model_id: str | None = Field(description="Saved model id, e.g. classification_xgboost_<time>.")
    rows: int = Field(description="Training rows.")
    features: list[str] = Field(description="Feature columns: every column except the target.")
    cv_metrics_mean: dict[str, float | None] = Field(
        description="Mean row of the PyCaret CV metrics, also stored in metadata.json."
    )


def train(args: TrainInput) -> CommandResult:
    namespace = _namespace(args.namespace)
    frame = read_frame(args.train)
    if args.target not in frame:
        raise ValueError(f"train requires target column {args.target!r}")
    root = data_manager(args.data_root).root
    registry = root / "models" / namespace
    features = [str(column) for column in frame.columns if column != args.target]
    plan = {
        "namespace": namespace,
        "registry_dir": str(registry),
        "rows": len(frame),
        "features": features,
    }
    if not args.write:
        return CommandResult(
            data=TrainData(dry_run=True, model_id=None, cv_metrics_mean={}, **plan)
        )
    from skills.ml.ml_engine import MLEngine

    engine = MLEngine(task=args.task, model_name=args.model_name, normalize=args.normalize)
    _, cv_metrics = engine.setup_and_train(
        frame,
        target=args.target,
        pca_components=args.pca_components,
        session_id=args.session_id,
        n_jobs=args.n_jobs,
        **args.create_kwargs,
    )
    mean = cv_metrics.loc["Mean"] if "Mean" in cv_metrics.index else cv_metrics.iloc[-1]
    metrics = json_safe({str(key): value for key, value in mean.to_dict().items()})
    model_id = engine.save_to_registry(
        namespace,
        train_data=frame,
        target=args.target,
        metrics=metrics,
        pca_components=args.pca_components,
        data_root=str(root),
    )
    return CommandResult(
        data=TrainData(dry_run=False, model_id=model_id, cv_metrics_mean=metrics, **plan),
        artifacts=[Artifact(name="model", path=str(registry / model_id), format="directory")],
    )


class PredictInput(OutputOptions):
    output: Path = Field(description="Destination predictions table.")
    data: Path = Field(description="Table of feature rows to predict.")
    namespace: str = Field(description="Registry namespace under data/models.")
    model_id: str = Field(
        description="Model id from `qs store list --kind models --namespace <namespace>`."
    )


class PredictData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: int = Field(description="Predicted rows.")
    task: str = Field(description="Task recorded in the model metadata.")
    columns: list[str] = Field(description="Prediction columns added by PyCaret.")


def predict(args: PredictInput) -> CommandResult:
    from skills.ml.ml_engine import MLEngine

    check_output(args.output, overwrite=args.overwrite, data_root=args.data_root)
    namespace = _namespace(args.namespace)
    root = str(data_manager(args.data_root).root)
    meta = next(
        (
            item
            for item in MLEngine.list_models(namespace, data_root=root)
            if item.get("model_id") == args.model_id
        ),
        None,
    )
    if meta is None:
        raise CLIError(
            "NOT_FOUND",
            f"Model not found: {namespace}/{args.model_id}",
            exit_code=3,
            hint=f"Run `uv run qs store list --kind models --namespace {namespace}` for saved models.",
        )
    engine = MLEngine(task=meta["task"], model_name=meta["model_name"], normalize=meta["normalize"])
    engine.load_from_registry(namespace, args.model_id, data_root=root)
    frame = read_frame(args.data)
    result = engine.predict(frame)
    added = [str(column) for column in result.columns if column not in frame.columns]
    artifact = write_frame(
        result, args.output, overwrite=args.overwrite, data_root=args.data_root, name="predictions"
    )
    return CommandResult(
        data=PredictData(rows=len(result), task=meta["task"], columns=added), artifacts=[artifact]
    )


COMMANDS = [
    Command(
        "ml.factor-rank",
        FactorRankInput,
        FactorRankData,
        factor_rank,
        "Train MLFactorEngine on factor features and write cross-sectional ranks.",
        side_effects=("writes-output",),
    ),
    Command(
        "ml.lasso-track",
        LassoInput,
        WeightsData,
        lasso,
        "Rolling LASSO index-tracking weights.",
        side_effects=("writes-output",),
    ),
    Command(
        "ml.folds",
        FoldsInput,
        FoldsData,
        folds,
        "Expanding walk-forward folds with label purge.",
    ),
    Command(
        "ml.pca-predict",
        PcaPredictInput,
        PcaPredictData,
        pca_predict,
        "Fit train-only PCA and a frozen regressor, then predict rows.",
        side_effects=("writes-output",),
    ),
    Command(
        "ml.train",
        TrainInput,
        TrainData,
        train,
        "Train a PyCaret MLEngine model and save it to the model registry.",
        side_effects=("writes-store",),
        priority="P2",
    ),
    Command(
        "ml.predict",
        PredictInput,
        PredictData,
        predict,
        "Predict with a registry model.",
        side_effects=("writes-output",),
        priority="P2",
    ),
]
