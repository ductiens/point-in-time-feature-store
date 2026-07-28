from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


CATALOG_PATH = Path("feature_catalog.yaml")
Aggregation = Literal["sum", "count", "time_since_last"]
SourceColumn = Literal["amount", "transaction_id", "event_ts"]
Entity = Literal["uid"]
EventTime = Literal["event_ts"]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
Version = Annotated[
    str,
    StringConstraints(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]

AGGREGATION_RULES: dict[
    str,
    tuple[str, int | None],
] = {
    "sum": ("amount", 0),
    "count": ("transaction_id", 0),
    "time_since_last": ("event_ts", None),
}


class FeatureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: Description
    entity: Entity
    aggregation: Aggregation
    source_column: SourceColumn
    window_hours: int = Field(gt=0)
    event_time: EventTime
    version: Version
    default_value: int | float | None

    @model_validator(mode="after")
    def validate_aggregation_semantics(self) -> "FeatureDefinition":
        expected_source, expected_default = AGGREGATION_RULES[
            self.aggregation
        ]
        if self.source_column != expected_source:
            raise ValueError(
                f"Aggregation '{self.aggregation}' requires "
                f"source_column '{expected_source}'."
            )
        if self.default_value != expected_default:
            raise ValueError(
                f"Aggregation '{self.aggregation}' requires "
                f"default_value {expected_default!r}."
            )
        return self


class FeatureCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Version
    features: list[FeatureDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_feature_names(self) -> "FeatureCatalog":
        names = [feature.name for feature in self.features]
        if len(names) != len(set(names)):
            raise ValueError("Feature names must be unique.")
        return self

    @property
    def max_lookback_hours(self) -> int:
        return max(feature.window_hours for feature in self.features)


def load_catalog(path: Path = CATALOG_PATH) -> FeatureCatalog:
    with path.open(encoding="utf-8") as catalog_file:
        raw_catalog = yaml.safe_load(catalog_file)

    if raw_catalog is None:
        raise ValueError(f"Catalog file is empty: {path}")

    return FeatureCatalog.model_validate(raw_catalog)


def main() -> None:
    catalog = load_catalog()
    print(f"catalog_version={catalog.version}")
    print(f"max_lookback_hours={catalog.max_lookback_hours}")
    for feature in catalog.features:
        print(
            f"{feature.name}@{feature.version}: "
            f"entity={feature.entity}, "
            f"aggregation={feature.aggregation}, "
            f"source_column={feature.source_column}, "
            f"window_hours={feature.window_hours}, "
            f"event_time={feature.event_time}, "
            f"default_value={feature.default_value!r}"
        )


if __name__ == "__main__":
    main()
